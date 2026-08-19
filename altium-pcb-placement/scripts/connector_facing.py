"""커넥터 개구부가 어느 쪽을 보는지 판정한다 (rot 0 기준).

IC 회전은 핀→변 매핑에서 나오지만 커넥터는 그 방법으로 안 나온다.
필요한 건 「개구부가 어디를 보는가」 하나다.

원리: 케이블이 들어가는 쪽에는 패드가 없고 하우징만 있다.
      패드 bbox 와 실크 bbox 를 따로 재서 실크가 더 튀어나온 쪽이 개구부다.
      데이터시트를 안 봐도 된다.

그 방향이 보드 바깥을 향하도록 회전을 정한다.
  개구부 −Y → 상변 rot 180 / 하변 rot 0 / 좌변 rot 270 / 우변 rot 90
"""
import argparse
import contextlib
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

from altium_monkey import AltiumPcbLib, AltiumSchDoc

MIL = 39.3700787402
IU = 10000.0


@contextlib.contextmanager
def quiet():
    b = io.StringIO()
    with contextlib.redirect_stdout(b), contextlib.redirect_stderr(b):
        yield b


def walk(o):
    for ch in getattr(o, 'children', []) or []:
        yield ch
        yield from walk(ch)


def sch_map(path):
    with quiet():
        doc = AltiumSchDoc(path)
        comps = list(doc.components)
    out = {}
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
            out.setdefault(des, fps[0])
    return out


def lib_index(dirs):
    idx = {}
    for d in dirs:
        for root, _s, files in os.walk(d):
            for f in files:
                if not f.lower().endswith('.pcblib'):
                    continue
                try:
                    with quiet():
                        lib = AltiumPcbLib.from_file(os.path.join(root, f))
                        for fp in lib.footprints:
                            idx.setdefault(fp.name.strip().lower(), fp)
                except Exception:
                    pass
    return idx


def ranges(fp):
    px, py, sx, sy = [], [], [], []
    for p in fp.pads:
        w, h = p.width / IU, p.height / IU
        px += [p.x_mils - w / 2, p.x_mils + w / 2]
        py += [p.y_mils - h / 2, p.y_mils + h / 2]
    for t in fp.primitives:
        if type(t).__name__ != 'AltiumPcbTrack':
            continue
        hw = t.width_mils / 2
        sx += [t.start_x_mils - hw, t.start_x_mils + hw,
               t.end_x_mils - hw, t.end_x_mils + hw]
        sy += [t.start_y_mils - hw, t.start_y_mils + hw,
               t.end_y_mils - hw, t.end_y_mils + hw]
    if not px or not sx:
        return None
    f = lambda v: (min(v) / MIL, max(v) / MIL)
    return f(px), f(py), f(sx), f(sy)


ROT_FOR_EDGE = {
    '-Y': {'top': 180, 'bottom': 0, 'left': 270, 'right': 90},
    '+Y': {'top': 0, 'bottom': 180, 'left': 90, 'right': 270},
    '-X': {'top': 90, 'bottom': 270, 'left': 0, 'right': 180},
    '+X': {'top': 270, 'bottom': 90, 'left': 180, 'right': 0},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('schdoc')
    ap.add_argument('--libs', nargs='+', required=True)
    ap.add_argument('--only', nargs='*', help='이 지정자만 (기본: J*/P*/CN*)')
    ap.add_argument('--min-overhang', type=float, default=0.5,
                    help='이 값보다 작으면 방향 불명으로 본다 (mm)')
    a = ap.parse_args()

    smap = sch_map(a.schdoc)
    idx = lib_index(a.libs)
    targets = a.only or [d for d in smap
                         if d[0] in 'JP' or d.upper().startswith('CN')]

    print(f'{"des":<5}{"개구부":<7}{"돌출 mm":<10}'
          f'{"상변":>5}{"하변":>5}{"좌변":>5}{"우변":>5}   풋프린트')
    for des in sorted(targets, key=lambda s: (s.rstrip('0123456789'),
                                              int(''.join(c for c in s if c.isdigit()) or 0))):
        fp = idx.get((smap.get(des) or '').strip().lower())
        if not fp:
            print(f'{des:<5}라이브러리에서 못 찾음')
            continue
        r = ranges(fp)
        if not r:
            print(f'{des:<5}프리미티브 부족')
            continue
        (a0, a1), (p0, p1), (b0, b1), (s0, s1) = r
        cand = {'-Y': p0 - s0, '+Y': s1 - p1, '-X': a0 - b0, '+X': b1 - a1}
        face, over = max(cand.items(), key=lambda kv: kv[1])
        if over < a.min_overhang:
            print(f'{des:<5}{"불명":<7}{over:>6.2f}    '
                  f'— 돌출이 작다. 도면으로 확인   {smap[des]}')
            continue
        e = ROT_FOR_EDGE[face]
        print(f'{des:<5}{face:<7}{over:>6.2f}    '
              f'{e["top"]:>5}{e["bottom"]:>5}{e["left"]:>5}{e["right"]:>5}   {smap[des]}')
    print('\n숫자 = 그 변에 놓을 때 줘야 할 rotation (반시계 도).')
    print('개구부가 보드 바깥을 향해야 한다. bbox 는 180° 회전으로 안 변하므로')
    print('겹침·외곽 검사에 안 걸린다 — 이 표로 따로 확인해야 한다.')


if __name__ == '__main__':
    main()
