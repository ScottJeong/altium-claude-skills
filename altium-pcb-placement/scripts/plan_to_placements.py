"""배치 가안 JSON → altium-mcp `place_components` 입력(mils).

가안은 mm·좌하단 원점·**bbox** 로 적혀 있고, Altium 은 mils·**컴포넌트 원점**을 쓴다.
그 둘은 같지 않다 — 풋프린트 원점은 pad1 일 수도, 몸체 중심일 수도, 엉뚱한 곳일 수도 있다.
실측 예: RJ45 는 원점이 bbox 중심에서 **7.70mm** 떨어져 있다.

`--libs` 를 주면 그 오차를 **라이브러리에서 직접 계산**한다. 회전각만큼 벡터를 돌려
더하므로 1패스로 끝난다. Altium 에 넣고 다시 읽어보는 왕복이 필요 없다.

  origin_to_place = 의도한_bbox중심 − rotate(풋프린트 원점→bbox중심, 배치회전)

--libs 없이 쓰면 bbox 중심을 원점으로 가정한다(옛 방식). 그 경우
--offsets 로 보정값(mils, {"U2": [dx, dy]})을 직접 줘야 한다.

출력은 그대로 place_components(placements=...) 에 넣을 JSON 이다.
"""
import argparse
import contextlib
import io
import json
import math
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

MIL = 39.3700787402      # 1 mm
IU = 10000.0             # Altium 내부단위 = 1/10000 mil


@contextlib.contextmanager
def _quiet():
    b = io.StringIO()
    with contextlib.redirect_stdout(b), contextlib.redirect_stderr(b):
        yield b


def _fp_bbox(fp):
    xs, ys = [], []
    for p in fp.pads:
        w, h = p.width / IU, p.height / IU
        xs += [p.x_mils - w / 2, p.x_mils + w / 2]
        ys += [p.y_mils - h / 2, p.y_mils + h / 2]
    for t in fp.primitives:
        if type(t).__name__ != 'AltiumPcbTrack':
            continue
        hw = t.width_mils / 2
        xs += [t.start_x_mils - hw, t.start_x_mils + hw,
               t.end_x_mils - hw, t.end_x_mils + hw]
        ys += [t.start_y_mils - hw, t.start_y_mils + hw,
               t.end_y_mils - hw, t.end_y_mils + hw]
    if not xs:
        return None
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def lib_offsets(schdoc, libdirs):
    """지정자 → 풋프린트 원점에서 bbox 중심까지의 벡터(mil, 회전 전)."""
    from altium_monkey import AltiumPcbLib, AltiumSchDoc

    def walk(o):
        for ch in getattr(o, 'children', []) or []:
            yield ch
            yield from walk(ch)

    with _quiet():
        doc = AltiumSchDoc(schdoc)
        comps = list(doc.components)
    des2fp = {}
    for c in comps:
        des, fps = None, []
        for ch in walk(c):
            t = type(ch).__name__
            if t == 'AltiumSchDesignator' and des is None:
                des = getattr(ch, 'text', None)
            elif t == 'AltiumSchImplementation':
                mn = getattr(ch, 'model_name', '') or ''
                mt = (getattr(ch, 'model_type', '') or '').upper()
                if mn and mt in ('PCBLIB', 'PCB', ''):
                    fps.append(mn)
        if des and fps:
            des2fp.setdefault(des, fps[0])

    idx = {}
    for d in libdirs:
        for root, _s, files in os.walk(d):
            for f in files:
                if not f.lower().endswith('.pcblib'):
                    continue
                try:
                    with _quiet():
                        lib = AltiumPcbLib.from_file(os.path.join(root, f))
                        for fp in lib.footprints:
                            idx.setdefault(fp.name.strip().lower(), fp)
                except Exception:
                    pass

    out = {}
    for des, fpn in des2fp.items():
        fp = idx.get(fpn.strip().lower())
        if not fp:
            continue
        c = _fp_bbox(fp)
        if c:
            out[des] = c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan')
    ap.add_argument('--schdoc', help='--libs 와 함께. 지정자→풋프린트 매핑용')
    ap.add_argument('--libs', nargs='*', help='.PcbLib 폴더. 원점 오차를 자동 계산한다')
    ap.add_argument('--offsets', help='수동 보정 JSON {"U2": [dx_mil, dy_mil]}')
    ap.add_argument('--only', nargs='*', help='이 지정자만')
    ap.add_argument('--origin', nargs=2, type=float, default=[0.0, 0.0],
                    metavar=('X_MM', 'Y_MM'),
                    help='보드 좌하단이 Altium 좌표계에서 어디인가 (mm). 기본 0,0')
    a = ap.parse_args()

    with open(a.plan, encoding='utf-8') as f:
        plan = json.load(f)

    auto = {}
    if a.libs:
        if not a.schdoc:
            sys.exit('--libs 를 쓰려면 --schdoc 도 줘야 한다')
        auto = lib_offsets(a.schdoc, a.libs)
        print(f'// 라이브러리에서 원점 오차 계산: {len(auto)}건', file=sys.stderr)

    manual = {}
    if a.offsets:
        with open(a.offsets, encoding='utf-8') as f:
            manual = json.load(f)

    ox, oy = a.origin
    out, skipped, nolib, big = [], [], [], []
    for c in plan.get('parts', []):
        des = (c.get('des') or '').strip()
        if not des or c.get('kind') == 'keepout':
            continue
        if '/' in des:               # "D1/D2" 같은 묶음 표기는 사람이 나눠야 한다
            skipped.append(des)
            continue
        if a.only and des not in a.only:
            continue
        rot = c.get('rot', 0)
        cx = (c['x'] + c['w'] / 2 + ox) * MIL
        cy = (c['y'] + c['h'] / 2 + oy) * MIL

        if des in auto:
            fx, fy = auto[des]
            ang = math.radians(rot)
            rx = fx * math.cos(ang) - fy * math.sin(ang)
            ry = fx * math.sin(ang) + fy * math.cos(ang)
            cx -= rx
            cy -= ry
            if abs(rx) > 20 or abs(ry) > 20:      # 0.5mm 넘는 오차는 알린다
                big.append((des, rx / MIL, ry / MIL))
        elif a.libs:
            nolib.append(des)

        dx, dy = manual.get(des, (0.0, 0.0))
        rec = {'designator': des, 'x': round(cx + dx, 2), 'y': round(cy + dy, 2),
               'rotation': rot}
        out.append(rec)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f'\n// {len(out)}개. rotation 은 반시계(CCW) 도 — place_components 규약과 같다.',
          file=sys.stderr)
    if big:
        print('// 원점이 bbox 중심과 크게 어긋난 부품 (자동 보정됨):', file=sys.stderr)
        for d, x, y in big:
            print(f'//   {d:<6} {x:+6.2f}, {y:+6.2f} mm', file=sys.stderr)
    if nolib:
        print(f'// [경고] 라이브러리에서 못 찾아 보정 못 함: {", ".join(nolib)}',
              file=sys.stderr)
    if skipped:
        print(f'// 묶음 표기라 건너뜀 (직접 나눠라): {", ".join(skipped)}', file=sys.stderr)


if __name__ == '__main__':
    main()
