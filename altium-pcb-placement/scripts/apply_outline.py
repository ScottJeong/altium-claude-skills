"""PcbDoc 에 보드 외곽(모서리 라운드) + 대칭 고정 M3 홀을 넣는다 (헤드리스).

**Altium 이 그 문서를 열고 있으면 안 된다.** 열려 있으면 Altium 이 저장하는 순간
여기서 쓴 내용이 덮인다. 사용자가 Ctrl+S 한 뒤에 돌리고, 끝나면 reload 하게 한다.

제자리 수정이면 `<파일>.bak` 을 먼저 만든다 (`--no-backup` 으로 끌 수 있다).

설계 규칙 두 가지가 여기 박혀 있다.
  - 외곽 모서리는 라운드. 직각 모서리는 취급 중 깨지고 사람이 베인다
  - 고정홀은 대칭. 비대칭이면 조립 지그·스페이서가 안 맞는다
"""
import argparse
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from altium_monkey import AltiumBoardOutline, AltiumPcbDoc, BoardOutlineVertex

def _need(path, what='입력', kind='file'):
    """경로를 검증한다. 없으면 스택 대신 한 줄로 알리고 끝낸다."""
    import os
    if kind == 'dir':
        if not os.path.isdir(path):
            sys.exit(f'[{what}] 폴더가 없다: {path}')
    else:
        if not os.path.isfile(path):
            sys.exit(f'[{what}] 파일이 없다: {path}')
    return path


MIL = 39.3700787402

HOLE_D_MM_DEFAULT = 3.2     # M3


def parse_holes(spec, w, h, margin):
    """--holes "15,3 87,3 87,97 15,97" 또는 None 이면 네 모서리에서 margin 만큼 안쪽."""
    if spec:
        out = []
        for t in spec.split():
            x, y = t.split(',')
            out.append((float(x), float(y)))
        return out
    return [(margin, margin), (w - margin, margin),
            (w - margin, h - margin), (margin, h - margin)]


def check_symmetry(holes):
    xs = sorted({round(x, 3) for x, _ in holes})
    ys = sorted({round(y, 3) for _, y in holes})
    ok = len(xs) == 2 and len(ys) == 2
    return ok, xs, ys


def rounded_rect(w, h, r):
    """좌하단 원점 직사각 + 4모서리 라운드. 반시계.

    세그먼트 종류는 시작 꼭짓점에 붙는다 — arc 꼭짓점은 다음 꼭짓점까지 호를 그린다.
    """
    W, H = w * MIL, h * MIL
    R = r * MIL
    return [
        BoardOutlineVertex(R, 0.0),
        BoardOutlineVertex(W - R, 0.0, True, W - R, R, R, 270.0, 360.0),
        BoardOutlineVertex(W, R),
        BoardOutlineVertex(W, H - R, True, W - R, H - R, R, 0.0, 90.0),
        BoardOutlineVertex(W - R, H),
        BoardOutlineVertex(R, H, True, R, H - R, R, 90.0, 180.0),
        BoardOutlineVertex(0.0, H - R),
        BoardOutlineVertex(0.0, R, True, R, R, R, 180.0, 270.0),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcbdoc')
    ap.add_argument('-o', '--out', help='출력 경로. 생략하면 제자리에 덮어쓴다')
    ap.add_argument('--width', type=float, required=True, help='보드 폭 mm')
    ap.add_argument('--height', type=float, required=True, help='보드 높이 mm')
    ap.add_argument('--corner-r', type=float, default=2.0,
                    help='모서리 라운드 반지름 mm. 0 이면 직각 (기본 2.0)')
    ap.add_argument('--holes', help='"x,y x,y ..." mm. 생략하면 네 모서리 --hole-margin')
    ap.add_argument('--hole-margin', type=float, default=3.0,
                    help='홀 중심을 변에서 이만큼 안쪽에 (기본 3.0)')
    ap.add_argument('--hole-dia', type=float, default=HOLE_D_MM_DEFAULT, help='홀 지름 mm')
    ap.add_argument('--no-holes', action='store_true')
    ap.add_argument('--no-backup', action='store_true',
                    help='제자리 수정 시 .bak 을 남기지 않는다')
    a = ap.parse_args()
    _need(a.pcbdoc, 'PcbDoc')
    dst = a.out or a.pcbdoc

    BOARD_W_MM, BOARD_H_MM = a.width, a.height
    CORNER_R_MM = a.corner_r
    HOLE_D_MM = PAD_D_MM = a.hole_dia
    HOLES_MM = [] if a.no_holes else parse_holes(a.holes, BOARD_W_MM, BOARD_H_MM,
                                                 a.hole_margin)
    ok, xs, ys = check_symmetry(HOLES_MM) if HOLES_MM else (True, [], [])
    if not ok:
        print(f'  [경고] 고정홀이 비대칭이다 — x={xs} y={ys}')
        print('         부품이 모서리를 먹으면 홀이 아니라 부품을 옮긴다')

    # 제자리 수정이면 백업을 먼저 뜬다. PcbDoc 은 되돌릴 방법이 없다.
    if dst == a.pcbdoc and not a.no_backup:
        bak = a.pcbdoc + '.bak'
        n = 1
        while os.path.exists(bak):
            bak = f'{a.pcbdoc}.bak{n}'
            n += 1
        shutil.copy2(a.pcbdoc, bak)
        print(f'백업 → {bak}')

    d = AltiumPcbDoc.from_file(a.pcbdoc)
    print(f'열기 OK — 부품 {len(d.components)}, 패드 {len(d.pads)}')

    # ⚠ 순서 주의 — `set_board_outline()` 은 오서링 빌더 상태를 스냅샷한다.
    # 그 뒤에 프리미티브 객체를 직접 고치면 저장에 반영되지 않는다.
    # 패드 먼저 고치고 외곽을 마지막에 설정한다.

    # 기존 자유 고정홀(부품 소속 아님)을 새 대칭 좌표로 옮긴다. 없으면 새로 만든다.
    free_mh = [p for p in d.pads
               if p.component_index is None and str(p.designator).startswith('MH')]
    print(f'기존 자유 고정홀 {len(free_mh)}개')
    for i, (hx, hy) in enumerate(HOLES_MM):
        if i < len(free_mh):
            p = free_mh[i]
            p.x = int(round(hx * MIL * 10000))
            p.y = int(round(hy * MIL * 10000))
            p.designator = f'MH{i + 1}'
            # 패드는 원본 바이너리를 캐시한다. 지워야 좌표 변경이 저장된다.
            p._raw_binary = None
            print(f'  이동 MH{i+1} → ({hx:g}, {hy:g})')
        else:
            d.add_pad(designator=f'MH{i + 1}',
                      position_mils=(hx * MIL, hy * MIL),
                      width_mils=PAD_D_MM * MIL, height_mils=PAD_D_MM * MIL,
                      layer='Multi-Layer', shape='ROUND',
                      hole_size_mils=HOLE_D_MM * MIL, plated=False)
            print(f'  신규 MH{i+1} → ({hx:g}, {hy:g})')

    d.save(dst)
    print('  (패스1 저장 — 패드)')

    # 패스2. 같은 세션에서 오서링 빌더를 건드리면 위의 직접 수정이 날아간다.
    # 반드시 다시 읽고 나서 외곽을 설정한다.
    d = AltiumPcbDoc.from_file(dst)
    d.set_board_outline(AltiumBoardOutline(
        vertices=rounded_rect(BOARD_W_MM, BOARD_H_MM, CORNER_R_MM)))
    print(f'외곽 {BOARD_W_MM:g} x {BOARD_H_MM:g} mm, 모서리 R{CORNER_R_MM:g}')
    d.save(dst)
    print(f'저장 → {dst}')

    v = AltiumPcbDoc.from_file(dst)
    br = v.board_regions[0]
    pts = [(round(p.x_raw / 10000 / MIL, 2), round(p.y_raw / 10000 / MIL, 2))
           for p in br.outline_vertices]
    print(f'\n검증 — 외곽 꼭짓점 {len(pts)}개(mm): {pts}')
    mh = [(p.designator, round(p.x_mils / MIL, 1), round(p.y_mils / MIL, 1))
          for p in v.pads
          if p.component_index is None and str(p.designator).startswith('MH')]
    print(f'검증 — 자유 고정홀: {mh}')
    xs = sorted({m[1] for m in mh})
    ys = sorted({m[2] for m in mh})
    print(f'검증 — 대칭? x={xs} y={ys}  → {"OK" if len(xs) == 2 and len(ys) == 2 else "비대칭"}')
    print(f'검증 — 부품 {len(v.components)}')


if __name__ == '__main__':
    main()
