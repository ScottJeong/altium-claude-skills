"""실크 지정자를 부품 외곽 바깥의 가장 가까운 빈 자리로 옮긴다.

Altium 의 `Reposition Selected Designators` 는 패드·타 실크 회피가 부실하다.
여기서는 패드 · 실크(트랙/아크/텍스트) · 이미 배치한 지정자를 전부 장애물로 놓고,
부품 외곽을 감싸는 링 위에서 **비용이 가장 낮은** 자리를 고른다.

  비용 = 부품 중심까지 거리
         + 대각 방향 벌점        (상하좌우를 선호)
         + 90° 회전 벌점         (가로쓰기를 선호)

「처음 비는 자리」를 잡으면 방향 순서 때문에 엉뚱하게 멀리 던져진다.
전 후보를 만들고 최소 비용을 고르는 게 핵심이다.

부품 외곽 = 패드 + 그 부품 자신의 실크 프리미티브. 패드만 쓰면 외곽선 위에 글자가 얹힌다.

한계: 스트로크 텍스트 폭은 문자당 폭을 높이 비율로 추정한다(CHAR_W).
      실제보다 좁게 잡으면 겹침을 놓치므로 여유를 크게 둔다.

사용:
    python place_designators.py <PcbDoc>                  # 계산만
    python place_designators.py <PcbDoc> --apply          # 반영
    python place_designators.py <PcbDoc> --max-offset 2.0 # 외곽에서 최대 이격
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from altium_monkey import AltiumPcbDoc

MM = 1 / 39.3700787402
IU = 10000.0
SILK = {'33': 'top', '34': 'bottom'}

CHAR_W = 0.62      # 문자 폭 / 높이 (여유 포함)
PAD_X = 0.08
PAD_Y = 0.05


def _need(p):
    if not os.path.exists(p):
        sys.exit(f'[입력] 경로가 없다: {p}')
    return p


def text_size(s, h, rot90):
    w = len(s) * CHAR_W * h + 2 * PAD_X
    hh = h + 2 * PAD_Y
    return (hh, w) if rot90 else (w, hh)


def hit(a, b, gap):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def seg_box(x1, y1, x2, y2, hw):
    return min(x1, x2) - hw, min(y1, y2) - hw, max(x1, x2) + hw, max(y1, y2) + hw


class Grid:
    def __init__(self, cell=2.0):
        self.cell = cell
        self.b = {}

    def add(self, r):
        for i in range(int(r[0] // self.cell), int(r[2] // self.cell) + 1):
            for j in range(int(r[1] // self.cell), int(r[3] // self.cell) + 1):
                self.b.setdefault((i, j), []).append(r)

    def near(self, r):
        out = []
        for i in range(int(r[0] // self.cell), int(r[2] // self.cell) + 1):
            for j in range(int(r[1] // self.cell), int(r[3] // self.cell) + 1):
                out.extend(self.b.get((i, j), ()))
        return out


def pad_box(p):
    cs = getattr(p, 'custom_shape', None)
    r = getattr(cs, 'region', None) if cs else None
    v = getattr(r, 'outline_vertices', None) if r is not None else None
    if v:
        xs = [q.x_mils * MM for q in v]
        ys = [q.y_mils * MM for q in v]
        return min(xs), min(ys), max(xs), max(ys)
    w, h = p.width / IU * MM, p.height / IU * MM
    x, y = p.x_mils * MM, p.y_mils * MM
    return x - w / 2, y - h / 2, x + w / 2, y + h / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pcbdoc')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--clearance', type=float, default=0.15)
    ap.add_argument('--max-offset', type=float, default=1.2,
                    help='부품 외곽에서 텍스트까지 최대 이격 mm')
    a = ap.parse_args()
    _need(a.pcbdoc)

    d = AltiumPcbDoc.from_file(a.pcbdoc)
    clr = a.clearance
    obst = {'top': Grid(), 'bottom': Grid()}

    # 패드: 관통홀이면 양면
    for j, c in enumerate(d.components):
        for p in d.get_component_primitives(j)['pads']:
            b = pad_box(p)
            lay = str(p.layer)
            if getattr(p, 'hole_size', 0) or lay not in ('1', '32'):
                obst['top'].add(b)
                obst['bottom'].add(b)
            else:
                obst['top' if lay == '1' else 'bottom'].add(b)
    # 실크 그래픽
    for t in d.tracks:
        s = SILK.get(str(t.layer))
        if s:
            obst[s].add(seg_box(t.start_x_mils * MM, t.start_y_mils * MM,
                                t.end_x_mils * MM, t.end_y_mils * MM,
                                t.width_mils * MM / 2))
    for arc in d.arcs:
        s = SILK.get(str(arc.layer))
        if s:
            r = arc.radius_mils * MM + arc.width_mils * MM / 2
            cx, cy = arc.center_x_mils * MM, arc.center_y_mils * MM
            obst[s].add((cx - r, cy - r, cx + r, cy + r))
    # 지정자가 아닌 실크 텍스트
    for t in d.texts:
        s = SILK.get(str(t.layer))
        if s and not t.is_designator and not t.is_comment:
            h = t.height_mils * MM
            w, hh = text_size('X' * 6, h, abs((t.rotation or 0) % 180 - 90) < 1)
            obst[s].add((t.x_mils * MM, t.y_mils * MM,
                         t.x_mils * MM + w, t.y_mils * MM + hh))

    # 부품 외곽 = 패드 + 자기 실크
    ext = {}
    for j, c in enumerate(d.components):
        pr = d.get_component_primitives(j)
        xs, ys = [], []
        for p in pr['pads']:
            b = pad_box(p)
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
        for t in pr['tracks']:
            if str(t.layer) in SILK:
                b = seg_box(t.start_x_mils * MM, t.start_y_mils * MM,
                            t.end_x_mils * MM, t.end_y_mils * MM, t.width_mils * MM / 2)
                xs += [b[0], b[2]]
                ys += [b[1], b[3]]
        for arc in pr['arcs']:
            if str(arc.layer) in SILK:
                r = arc.radius_mils * MM + arc.width_mils * MM / 2
                xs += [arc.center_x_mils * MM - r, arc.center_x_mils * MM + r]
                ys += [arc.center_y_mils * MM - r, arc.center_y_mils * MM + r]
        if xs:
            ext[j] = (min(xs), min(ys), max(xs), max(ys))

    des = [t for t in d.texts if t.is_designator and str(t.layer) in SILK]
    # 작은 부품부터 — 자리가 빠듯한 쪽을 먼저 확보한다
    des.sort(key=lambda t: (lambda b: (b[2] - b[0]) * (b[3] - b[1]) if b else 0)(
        ext.get(t.component_index)))

    placed = {'top': Grid(), 'bottom': Grid()}
    plan = []
    keep = moved = fail = 0
    DIRS = [(0, 1, 0.0), (0, -1, 0.0), (-1, 0, 0.15), (1, 0, 0.15),
            (-1, 1, 0.8), (1, 1, 0.8), (-1, -1, 0.8), (1, -1, 0.8)]

    for t in des:
        s = SILK[str(t.layer)]
        ci = t.component_index
        label = d.components[ci].designator if ci is not None and ci < len(d.components) else 'XX'
        h = t.height_mils * MM
        rot90 = abs((t.rotation or 0) % 180 - 90) < 1
        w, hh = text_size(label, h, rot90)
        x0, y0 = t.x_mils * MM, t.y_mils * MM
        cur = (x0 - PAD_X, y0 - PAD_Y, x0 - PAD_X + w, y0 - PAD_Y + hh)

        def clash(box):
            for r in obst[s].near(box) + placed[s].near(box):
                if hit(box, r, clr):
                    return True
            return False

        if not clash(cur):
            placed[s].add(cur)
            keep += 1
            continue
        b = ext.get(ci)
        if b is None:
            fail += 1
            continue
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        best = None
        for r90 in (False, True):
            ww, hhh = text_size(label, h, r90)
            for dx, dy, pen in DIRS:
                off = clr
                while off <= a.max_offset + 1e-9:
                    ox = (b[2] + off) if dx > 0 else ((b[0] - off - ww) if dx < 0 else cx - ww / 2)
                    oy = (b[3] + off) if dy > 0 else ((b[1] - off - hhh) if dy < 0 else cy - hhh / 2)
                    box = (ox, oy, ox + ww, oy + hhh)
                    if not clash(box):
                        # 원래 자리에서 얼마나 움직이는가가 비용이다.
                        # 부품 중심까지 거리로 재면 큰 부품은 어느 자리든 멀어서
                        # 반대편으로 튀어버린다 (SW 류가 10mm 넘게 이동했다).
                        cost = (math.hypot(ox - (x0 - PAD_X), oy - (y0 - PAD_Y))
                                + pen + (0.6 if r90 != rot90 else 0.0))
                        if best is None or cost < best[0]:
                            best = (cost, box, r90)
                        break
                    off += 0.2
        if best:
            _, box, r90 = best
            placed[s].add(box)
            moved += 1
            plan.append((t, label, x0, y0, box[0] + PAD_X, box[1] + PAD_Y,
                         90.0 if r90 else 0.0,
                         math.hypot(box[0] + PAD_X - x0, box[1] + PAD_Y - y0)))
        else:
            placed[s].add(cur)
            fail += 1
            plan.append((t, label, x0, y0, None, None, None, None))

    print(f'  지정자 {len(des)}   유지 {keep}   이동 {moved}   자리없음 {fail}')
    mv = [p for p in plan if p[4] is not None]
    if mv:
        ds = sorted(p[7] for p in mv)
        print(f'  이동거리  중앙값 {ds[len(ds)//2]:.2f}mm   최대 {ds[-1]:.2f}mm')
        rot = sum(1 for p in mv if p[6] == 90.0)
        print(f'  90도 회전 {rot}개')
        for t, lab, ox, oy, nx, ny, rr, dd in sorted(mv, key=lambda z: -z[7])[:10]:
            print(f'   {lab:6} ({ox:6.2f},{oy:6.2f}) → ({nx:6.2f},{ny:6.2f}) rot={rr:.0f}  {dd:5.2f}mm')
    nf = [p for p in plan if p[4] is None]
    if nf:
        print(f'  자리 못 찾음 {len(nf)} — 원위치 유지, 육안 정리 대상')
        print('   ' + '  '.join(f'{p[1]}' for p in nf[:20]))

    if not a.apply:
        print('\n  계산만 했다. 반영하려면 --apply')
        return
    bak = f'{a.pcbdoc}.bak-des-{time.strftime("%H%M%S")}'
    shutil.copy2(a.pcbdoc, bak)
    print(f'  백업 {os.path.basename(bak)}')
    for t, lab, ox, oy, nx, ny, rr, dd in plan:
        if nx is None:
            continue
        t.x = int(round(nx / MM * IU))
        t.y = int(round(ny / MM * IU))
        t.rotation = rr
    d.save(a.pcbdoc)
    print('  저장 완료')


if __name__ == '__main__':
    main()
