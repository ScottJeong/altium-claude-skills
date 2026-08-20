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


def side(c):
    """부품이 놓인 면. 'top' / 'bottom'."""
    try:
        return str(c.get_layer_normalized()).lower()
    except Exception:
        return str(getattr(c, 'layer', '')).lower()


def tht_boxes(d, i):
    """관통홀 패드 **하나씩**의 bbox 목록. 홀은 판을 뚫으므로 반대면과도 부딪친다.

    이게 없으면 반대면 판정이 '층이 다르니 무조건 안전' 이 되어,
    THT 핀 위에 반대면 부품을 올려놓는 것을 못 잡는다.

    합쳐서 하나의 bbox 로 만들면 안 된다 — 네 모서리에 기구홀이 있는 소켓은
    합친 bbox 가 몸체 전체가 되어 그 아래 전부를 오탐으로 잡는다.
    """
    out = []
    for p in d.get_component_primitives(i)['pads']:
        if not getattr(p, 'hole_size', 0):
            continue
        w, h = p.width / IU, p.height / IU
        out.append((p.x_mils - w / 2, p.y_mils - h / 2,
                    p.x_mils + w / 2, p.y_mils + h / 2))
    return out


def _cross(b1, b2, g):
    """두 bbox 의 x·y 겹침량. 둘 다 양수면 교차."""
    if b1 is None or b2 is None:
        return None
    ox = min(b1[2], b2[2]) - max(b1[0], b2[0]) + g
    oy = min(b1[3], b2[3]) - max(b1[1], b2[1]) + g
    return (ox, oy) if ox > 0 and oy > 0 else None


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
            boxes.append((c.source_designator, b, side(c), tht_boxes(d, i)))
    n_bot = sum(1 for x in boxes if 'bottom' in x[2])
    print(f'부품 {len(d.components)} / bbox 산출 {len(boxes)}'
          f'  (top {len(boxes) - n_bot} / bottom {n_bot})'
          f'  ({"패드만" if a.pads_only else "패드+실크"}, 요구간격 {a.gap:g}mm)')

    g = a.gap * MIL
    hits, cross = [], []
    for i in range(len(boxes)):
        n1, b1, s1, t1 = boxes[i]
        for j in range(i + 1, len(boxes)):
            n2, b2, s2, t2 = boxes[j]
            if s1 == s2:
                ov = _cross(b1, b2, g)
                if ov:
                    hits.append((min(ov) / MIL, n1, n2, ov[0] / MIL, ov[1] / MIL, s1))
                continue
            # 반대면 — 관통홀 하나라도 상대 영역을 침범할 때만 충돌이다
            worst = None
            for tbs, other, owner in ((t1, b2, n1), (t2, b1, n2)):
                for tb in tbs:
                    ov = _cross(tb, other, g)
                    if ov and (worst is None or min(ov) > worst[0]):
                        worst = (min(ov), ov[0], ov[1], owner)
            if worst:
                cross.append((worst[0] / MIL, n1, n2,
                              worst[1] / MIL, worst[2] / MIL, worst[3]))
    hits.sort(reverse=True)
    cross.sort(reverse=True)

    print(f'\n=== 같은 면 겹침 {len(hits)}')
    for _, n1, n2, ox, oy, s in hits[:60]:
        print(f'  {n1:<6} ↔ {n2:<6} [{s:6}]  겹침 x {ox:5.2f}  y {oy:5.2f} mm')
    if len(hits) > 60:
        print(f'  ... 외 {len(hits) - 60}쌍')

    print(f'\n=== 반대면 관통홀 충돌 {len(cross)}')
    for _, n1, n2, ox, oy, owner in cross[:30]:
        print(f'  {n1:<6} ↔ {n2:<6}  {owner} 의 관통홀이 침범  x {ox:5.2f}  y {oy:5.2f} mm')
    if len(cross) > 30:
        print(f'  ... 외 {len(cross) - 30}쌍')
    if not cross:
        print('  없음. 반대면끼리 XY 가 겹치는 것은 정상이다 '
              '(bottom 디커플링이 그렇게 놓인다)')

    # 보드 밖
    br = d.board_regions[0]
    vs = [(p.x_raw / IU, p.y_raw / IU) for p in br.outline_vertices]
    bx0, by0 = min(v[0] for v in vs), min(v[1] for v in vs)
    bx1, by1 = max(v[0] for v in vs), max(v[1] for v in vs)
    print(f'\n=== 보드 외곽 {bx0/MIL:.1f},{by0/MIL:.1f} ~ {bx1/MIL:.1f},{by1/MIL:.1f} mm')

    def outside(b):
        return b[0] < bx0 - 1 or b[1] < by0 - 1 or b[2] > bx1 + 1 or b[3] > by1 + 1

    hard, soft = [], []
    for i, c in enumerate(d.components):
        bp = bbox(d, i, True)          # 패드만
        bf = bbox(d, i, False)         # 패드 + 실크
        if bp and outside(bp):
            hard.append((c.source_designator, bp))
        elif bf and outside(bf):
            soft.append((c.source_designator, bf))

    print(f'패드가 보드 밖 {len(hard)}  ← 제조 불가. 반드시 고친다')
    for n, b in hard:
        print(f'  {n:<6} x {b[0]/MIL:7.2f}..{b[2]/MIL:7.2f}   y {b[1]/MIL:7.2f}..{b[3]/MIL:7.2f}')
    print(f'실크·하우징만 보드 밖 {len(soft)}  ← 엣지 커넥터면 정상. 눈으로 확인')
    for n, b in soft:
        print(f'  {n:<6} x {b[0]/MIL:7.2f}..{b[2]/MIL:7.2f}   y {b[1]/MIL:7.2f}..{b[3]/MIL:7.2f}')


if __name__ == '__main__':
    main()
