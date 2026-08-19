"""배치 후 물리 충돌 검사 — 부품 bbox 교차 + 보드 밖으로 나간 것.

DRC 는 넷·클리어런스를 보지만 배치 단계에서 필요한 건 "부품끼리 겹쳤나" 다.
프리미티브 좌표는 이미 회전이 반영된 절대좌표라 그대로 bbox 를 뜨면 된다.
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from altium_monkey import AltiumPcbDoc

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
IU = 10000.0


def bbox(d, i, pads_only):
    pr = d.get_component_primitives(i)
    xs, ys = [], []
    for p in pr['pads']:
        w, h = p.width / IU, p.height / IU
        xs += [p.x_mils - w / 2, p.x_mils + w / 2]
        ys += [p.y_mils - h / 2, p.y_mils + h / 2]
    if not pads_only:
        for t in pr['tracks']:
            hw = t.width_mils / 2
            xs += [t.start_x_mils - hw, t.start_x_mils + hw,
                   t.end_x_mils - hw, t.end_x_mils + hw]
            ys += [t.start_y_mils - hw, t.start_y_mils + hw,
                   t.end_y_mils - hw, t.end_y_mils + hw]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcbdoc')
    ap.add_argument('--pads-only', action='store_true',
                    help='실크 제외, 패드만으로 판정 (실크 겹침은 무해할 때가 많다)')
    ap.add_argument('--gap', type=float, default=0.0,
                    help='요구 최소 간격 mm. 0 이면 실제 교차만')
    a = ap.parse_args()
    _need(a.pcbdoc, 'PcbDoc')

    d = AltiumPcbDoc.from_file(a.pcbdoc)
    boxes = []
    for i, c in enumerate(d.components):
        b = bbox(d, i, a.pads_only)
        if b:
            boxes.append((c.source_designator, b))
    print(f'부품 {len(d.components)} / bbox 산출 {len(boxes)}'
          f'  ({"패드만" if a.pads_only else "패드+실크"}, 요구간격 {a.gap:g}mm)')

    g = a.gap * MIL
    hits = []
    for i in range(len(boxes)):
        n1, (a1, b1, c1, d1) = boxes[i]
        for j in range(i + 1, len(boxes)):
            n2, (a2, b2, c2, d2) = boxes[j]
            ox = min(c1, c2) - max(a1, a2) + g
            oy = min(d1, d2) - max(b1, b2) + g
            if ox > 0 and oy > 0:
                hits.append((min(ox, oy) / MIL, n1, n2, ox / MIL, oy / MIL))
    hits.sort(reverse=True)

    print(f'\n=== 겹치는 쌍 {len(hits)}')
    for depth, n1, n2, ox, oy in hits[:60]:
        print(f'  {n1:<6} ↔ {n2:<6}  겹침 x {ox:5.2f}  y {oy:5.2f} mm')
    if len(hits) > 60:
        print(f'  ... 외 {len(hits) - 60}쌍')

    # 보드 밖
    br = d.board_regions[0]
    vs = [(p.x_raw / IU, p.y_raw / IU) for p in br.outline_vertices]
    bx0, by0 = min(v[0] for v in vs), min(v[1] for v in vs)
    bx1, by1 = max(v[0] for v in vs), max(v[1] for v in vs)
    print(f'\n=== 보드 외곽 {bx0/MIL:.1f},{by0/MIL:.1f} ~ {bx1/MIL:.1f},{by1/MIL:.1f} mm')
    out = []
    for n, (a1, b1, c1, d1) in boxes:
        if a1 < bx0 - 1 or b1 < by0 - 1 or c1 > bx1 + 1 or d1 > by1 + 1:
            out.append((n, a1 / MIL, b1 / MIL, c1 / MIL, d1 / MIL))
    print(f'외곽 밖으로 나간 부품 {len(out)}')
    for n, x0, y0, x1, y1 in out:
        print(f'  {n:<6} x {x0:7.2f}..{x1:7.2f}   y {y0:7.2f}..{y1:7.2f}')


if __name__ == '__main__':
    main()
