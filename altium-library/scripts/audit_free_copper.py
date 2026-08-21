"""풋프린트 구리층의 자유 프리미티브를 찾는다 — 배선이 못 들어오는 원인 1순위.

구리층(Top/Bottom)에 놓인 region·arc·track·fill 은 **넷이 없다.**
라우터는 넷 있는 트랙을 넷 없는 구리에 붙이지 못한다. 그래서 패드가 그 구리 안에
묻혀 있으면 바깥에서 오는 배선이 패드에 닿기 전에 거부된다.

증상이 방향 문제로 보인다:
    다른 패드 → 이 패드   안 된다
    이 패드   → 다른 패드   된다
패드에서 출발하면 자기 구리 위에서 시작하는 거라 그냥 나가기 때문이다.
라우터 버그나 레이어 문제로 오해하기 쉬우니 먼저 이걸 돌린다.

패드가 자유 구리에 **덮여 있는지**까지 본다. 덮여 있으면 배선 불가로 판정한다.

사용:
    python audit_free_copper.py <PcbLib 파일 또는 폴더> [--only NAME ...]
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from altium_monkey import AltiumPcbLib

MIL = 0.0254          # 1 mil = 0.0254 mm
IU = 10000.0          # 내부단위 → mil
COPPER = (1, 32)      # Top, Bottom


def _need(path, what='입력'):
    if not os.path.exists(path):
        sys.exit(f'[{what}] 경로가 없다: {path}')
    return path


def _bbox_pts(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def free_copper(fp):
    """구리층 자유 프리미티브 목록. 커스텀 패드의 형상 region 은 제외한다."""
    shape_regions = set()
    for pd in fp.pads:
        cs = getattr(pd, 'custom_shape', None)
        if cs is not None and getattr(cs, 'region', None) is not None:
            shape_regions.add(id(cs.region))
    # PADINDEX 를 가진 region 도 패드 형상이다 (custom_shape.region 이 첫 개만 주는 버그 우회)
    out = []
    for p in fp.primitives:
        if type(p).__name__.endswith('Pad'):
            continue
        if getattr(p, 'layer', None) not in COPPER:
            continue
        if id(p) in shape_regions:
            continue
        if (getattr(p, 'properties', None) or {}).get('PADINDEX'):
            continue
        out.append(p)
    return out


def prim_bbox(p):
    if getattr(p, 'outline_vertices', None):
        return _bbox_pts([(v.x_mils * MIL, v.y_mils * MIL) for v in p.outline_vertices])
    if hasattr(p, 'center_x_mils'):                       # arc
        r = p.radius_mils * MIL + (p.width_mils * MIL) / 2
        cx, cy = p.center_x_mils * MIL, p.center_y_mils * MIL
        return cx - r, cy - r, cx + r, cy + r
    if hasattr(p, 'start_x_mils'):                        # track
        hw = p.width_mils * MIL / 2
        xs = [p.start_x_mils * MIL, p.end_x_mils * MIL]
        ys = [p.start_y_mils * MIL, p.end_y_mils * MIL]
        return min(xs) - hw, min(ys) - hw, max(xs) + hw, max(ys) + hw
    return None


def pad_bbox(pd):
    w, h = pd.width / IU * MIL, pd.height / IU * MIL
    x, y = pd.x_mils * MIL, pd.y_mils * MIL
    return x - w / 2, y - h / 2, x + w / 2, y + h / 2


def covers(outer, inner):
    """outer 가 inner 를 완전히 품는가."""
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def audit(path, only=None):
    lib = AltiumPcbLib.from_file(path)
    bad = 0
    for fp in lib.footprints:
        if only and fp.name not in only:
            continue
        cu = free_copper(fp)
        if not cu:
            continue
        boxes = [(p, prim_bbox(p)) for p in cu]
        buried = []
        for pd in fp.pads:
            if pd.layer not in COPPER:
                continue
            pb = pad_bbox(pd)
            for p, b in boxes:
                if b and covers(b, pb):
                    buried.append((pd.designator, type(p).__name__.replace('AltiumPcb', '')))
                    break
        bad += 1
        mark = '배선 불가' if buried else '주의'
        print(f'  [{mark}] {os.path.basename(path)} :: {fp.name}')
        kinds = {}
        for p in cu:
            k = type(p).__name__.replace('AltiumPcb', '')
            kinds[k] = kinds.get(k, 0) + 1
        print(f'      구리층 자유 프리미티브 {len(cu)}개 {kinds}')
        if buried:
            for des, kind in buried:
                print(f'      패드 {des} 가 {kind} 에 덮여 있다 → 바깥에서 배선이 못 들어온다')
        else:
            print('      패드는 덮이지 않았다. 넷 없는 구리로 남으므로 pour 와 DRC 만 확인')
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='.PcbLib 파일 또는 폴더')
    ap.add_argument('--only', nargs='*', help='이 풋프린트만')
    a = ap.parse_args()
    _need(a.path, 'PcbLib')

    files = ([a.path] if os.path.isfile(a.path)
             else sorted(f for f in
                         (os.path.join(a.path, x) for x in os.listdir(a.path))
                         if f.lower().endswith('.pcblib')))
    if not files:
        sys.exit(f'[PcbLib] .PcbLib 이 없다: {a.path}')

    total = 0
    for f in files:
        try:
            total += audit(f, set(a.only) if a.only else None)
        except Exception as e:
            print(f'  [건너뜀] {os.path.basename(f)}: {e}')
    print(f'\n구리층 자유 프리미티브를 가진 풋프린트 {total}개')
    if total:
        print('구리는 패드여야 한다. SKILL.md §4-B 참고.')


if __name__ == '__main__':
    main()
