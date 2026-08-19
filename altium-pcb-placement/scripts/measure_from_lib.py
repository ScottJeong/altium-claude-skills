"""회로도 + 라이브러리 폴더만으로 풋프린트 실측.

PcbDoc(=Update PCB) 없이도 된다. 회로도가 참조하는 풋프린트 이름을 뽑고,
그 이름을 라이브러리 .PcbLib 에서 찾아 bbox 를 잰다.

사용:
  python measure_from_lib.py <SchDoc> --libs <폴더> [...] [--only U2 U3 ...]
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
                p = os.path.join(root, f)
                try:
                    with quiet():
                        lib = AltiumPcbLib.from_file(p)
                        for fp in lib.footprints:
                            idx.setdefault(fp.name.strip().lower(), (f, fp))
                except Exception as e:
                    print(f'  [경고] {f} 열기 실패 ({type(e).__name__})')
    return idx


def bbox(fp, pads_only=False):
    xs, ys = [], []
    for p in fp.pads:
        w, h = p.width / IU, p.height / IU
        xs += [p.x_mils - w / 2, p.x_mils + w / 2]
        ys += [p.y_mils - h / 2, p.y_mils + h / 2]
    if not pads_only:
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
    return min(xs), min(ys), max(xs), max(ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('schdoc')
    ap.add_argument('--libs', nargs='+', required=True)
    ap.add_argument('--only', nargs='*')
    a = ap.parse_args()

    smap = sch_map(a.schdoc)
    idx = lib_index(a.libs)
    print(f'회로도 부품 {len(smap)} / 라이브러리 풋프린트 {len(idx)}종\n')
    print(f'{"des":<6}{"footprint":<34}{"W x H (mm)":<20}{"패드만":<18}라이브러리')
    miss = []
    for des in sorted(smap, key=lambda s: (s.rstrip('0123456789'),
                                           int(''.join(c for c in s if c.isdigit()) or 0))):
        if a.only and des not in a.only:
            continue
        fpn = smap[des]
        hit = idx.get(fpn.strip().lower())
        if not hit:
            miss.append((des, fpn))
            continue
        libf, fp = hit
        b, bp = bbox(fp), bbox(fp, True)
        if not b:
            print(f'{des:<6}{fpn[:33]:<34}(프리미티브 없음)')
            continue
        w, h = (b[2] - b[0]) / MIL, (b[3] - b[1]) / MIL
        pw, ph = ((bp[2] - bp[0]) / MIL, (bp[3] - bp[1]) / MIL) if bp else (0, 0)
        print(f'{des:<6}{fpn[:33]:<34}{w:7.2f} x {h:6.2f}   {pw:6.2f} x {ph:6.2f}   {libf}')
    if miss:
        print(f'\n라이브러리에서 못 찾음 {len(miss)}건')
        for d, f in miss[:20]:
            print(f'  {d:<6} {f}')


if __name__ == '__main__':
    main()
