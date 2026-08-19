"""기준 심볼/풋프린트와 내가 만든 것을 3층으로 비교한다.

속성만 비교하면 "일치" 라고 나오는데 Altium 화면은 딴판일 수 있다. 실제로 그랬다.
색·z-order·핀번호 표시는 아래 2층·3층에서만 잡힌다.

  1층 파싱된 속성   좌표, 길이, 방향, 전기타입, 색
  2층 레코드 순서   z-order 가 여기서 결정된다 (채워진 사각형이 핀 뒤면 이름을 덮는다)
  3층 원시 바이트   플래그 비트

사용:
    # 심볼
    python diff_symbol.py --ref house.SchLib "HRS PART" --new mine.SchLib "PART"

    # 풋프린트
    python diff_symbol.py --pcb --ref house.PcbLib "REF-FP" --new mine.PcbLib "FP"
"""

import argparse
import sys
from collections import Counter

# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


try:
    from altium_monkey import AltiumPcbLib, AltiumSchLib
except ImportError:  # pragma: no cover
    sys.exit('altium_monkey 가 없다. 그 패키지가 설치된 Python 3.12 venv 로 실행하라.')

SKIP_ATTRS = {'parent', 'get_end_location', 'get_hot_spot', 'get_text_y_offset',
              'format_info', 'to_svg', 'serialize_to_binary', 'serialize_to_record',
              'parse_from_binary', 'parse_from_record', 'raw_records',
              'get_all_records', 'unique_id', 'index_in_sheet'}

RECORD_NAMES = {'1': 'component', '2': 'pin', '14': 'rectangle', '34': 'designator',
                '41': 'parameter', '44': 'impl-list', '45': 'impl', '46': 'impl-map',
                '48': 'impl-param', '4': 'label', '6': 'polyline', '13': 'line'}


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ref', nargs=2, required=True, metavar=('LIB', 'NAME'))
    ap.add_argument('--new', nargs=2, required=True, metavar=('LIB', 'NAME'))
    ap.add_argument('--pcb', action='store_true', help='풋프린트 비교 (기본은 심볼)')
    ap.add_argument('--key', default=None,
                    help='바이트 비교할 핀/패드 지정자. 생략하면 첫 번째')
    return ap.parse_args()


def load_symbol(path, name):
    sym = AltiumSchLib(path).get_symbol(name)
    if sym is None:
        avail = AltiumSchLib.get_symbol_names(path)
        sys.exit(f'{path} 에 {name!r} 이 없다. 있는 것: {avail[:20]}')
    return sym


def load_footprint(path, name):
    lib = AltiumPcbLib.from_file(path)
    for f in lib.footprints:
        if f.name == name:
            return f
    sys.exit(f'{path} 에 {name!r} 이 없다. 있는 것: {[f.name for f in lib.footprints][:20]}')


def diff_attrs(a, b, label):
    print(f'\n=== 1층: {label} 속성 ===')
    names = sorted(n for n in dir(a)
                   if not n.startswith('_') and n not in SKIP_ATTRS)
    hits = 0
    for n in names:
        try:
            x, y = getattr(a, n), getattr(b, n)
        except Exception:
            continue
        if callable(x):
            continue
        if repr(x) != repr(y):
            print(f'  {n:32s} ref={repr(x)[:30]:32s} new={repr(y)[:30]}')
            hits += 1
    print('  (차이 없음)' if not hits else f'  -> {hits}개 다름')


def record_runs(sym):
    seq = [str(r.get('RECORD')) for r in sym.raw_records if isinstance(r, dict)]
    runs, cur, n = [], None, 0
    for r in seq:
        if r == cur:
            n += 1
        else:
            if cur is not None:
                runs.append((cur, n))
            cur, n = r, 1
    if cur is not None:
        runs.append((cur, n))
    return runs


def fmt_runs(runs):
    return '  '.join(f'{k}x{v}' for k, v in runs)


def diff_order(ref, new):
    print('\n=== 2층: 레코드 순서 (z-order) ===')
    a, b = record_runs(ref), record_runs(new)
    print(f'  ref : {fmt_runs(a)}')
    print(f'  new : {fmt_runs(b)}')
    print('  ' + '  '.join(f'{k}={v}' for k, v in RECORD_NAMES.items()
                           if any(k == r for r, _ in a + b)))
    ka = [k for k, _ in a if k in ('2', '14')]
    kb = [k for k, _ in b if k in ('2', '14')]
    if ka != kb:
        print('  !! 핀(2)/사각형(14) 순서가 다르다. 채워진 사각형이 핀 뒤면')
        print('     Altium 이 핀 이름 글자를 덮어버린다. 좌표로는 안 잡히는 결함이다.')
    else:
        print('  핀/사각형 순서 동일')


def pin_blob(sym, key):
    pins = list(sym.pins)
    idx = 0
    if key:
        idx = next((i for i, p in enumerate(pins) if p.designator == key), 0)
    recs = [r for r in sym.raw_records
            if isinstance(r, dict) and str(r.get('RECORD')) == '2']
    if idx >= len(recs):
        return None, None
    return pins[idx].designator, recs[idx].get('__BINARY_DATA__')


def diff_bytes(ref, new, key):
    print('\n=== 3층: 핀 원시 바이트 ===')
    da, ba = pin_blob(ref, key)
    db, bb = pin_blob(new, key)
    if ba is None or bb is None:
        print('  바이너리 레코드를 못 찾음')
        return
    print(f'  ref {da}: {len(ba)}B   new {db}: {len(bb)}B')
    if ba == bb:
        print('  바이트 완전 동일')
        return
    print(f'  ref {ba.hex(" ")}')
    print(f'  new {bb.hex(" ")}')
    for i in range(max(len(ba), len(bb))):
        x = ba[i] if i < len(ba) else None
        y = bb[i] if i < len(bb) else None
        if x != y:
            note = ''
            if i == 15 and x is not None and y is not None:
                bits = {0x08: '핀 이름 표시', 0x10: '핀 번호 표시',
                        0x20: 'is_not_accessible'}
                d = x ^ y
                note = '  <- ' + ', '.join(v for k, v in bits.items() if d & k)
            print(f'  offset {i:3d}: ref=0x{x:02X} new=0x{y:02X}{note}'
                  if x is not None and y is not None
                  else f'  offset {i:3d}: 길이 다름')


def diff_symbols(ref, new, key):
    print(f'ref = {ref.name}   new = {new.name}')
    print(f'part_count  ref={ref.part_count}  new={new.part_count}')
    pr, pn = list(ref.pins), list(new.pins)
    print(f'pin count   ref={len(pr)}  new={len(pn)}')
    print(f'파트별 핀수 ref={dict(sorted(Counter(p.owner_part_id for p in pr).items()))}'
          f'  new={dict(sorted(Counter(p.owner_part_id for p in pn).items()))}')

    dr = {p.designator for p in pr}
    dn = {p.designator for p in pn}
    if dr != dn:
        print(f'  ref 에만: {sorted(dr - dn)[:12]}')
        print(f'  new 에만: {sorted(dn - dr)[:12]}')

    a = next((p for p in pr if p.designator == (key or pr[0].designator)), pr[0])
    b = next((p for p in pn if p.designator == a.designator), pn[0])
    diff_attrs(a, b, f'핀 {a.designator}')

    if list(ref.rectangles) and list(new.rectangles):
        diff_attrs(list(ref.rectangles)[0], list(new.rectangles)[0], '본체 사각형')

    print('\n--- 지정자 / 파라미터 ---')
    for tag, s in (('ref', ref), ('new', new)):
        for d in s.designators:
            print(f'  {tag} designator {d.text!r} at ({d.location.x},{d.location.y})')
        for p in s.parameters:
            print(f'  {tag} param {p.name!r}={str(p.text)[:24]!r} '
                  f'at ({p.location.x},{p.location.y}) hidden={p.is_hidden}')
    print(f'  ref 풋프린트 링크 {[i.model_name for i in ref.implementations]}')
    print(f'  new 풋프린트 링크 {[i.model_name for i in new.implementations]}')

    diff_order(ref, new)
    diff_bytes(ref, new, key)


def diff_footprints(ref, new, key):
    print(f'ref = {ref.name}   new = {new.name}')
    pr, pn = list(ref.pads), list(new.pads)
    print(f'pad count  ref={len(pr)}  new={len(pn)}')
    print(f'track      ref={len(list(ref.tracks))}  new={len(list(new.tracks))}')
    dr = {p.designator for p in pr}
    dn = {p.designator for p in pn}
    if dr != dn:
        print(f'  ref 에만: {sorted(dr - dn)[:12]}')
        print(f'  new 에만: {sorted(dn - dr)[:12]}')
    if pr and pn:
        a = next((p for p in pr if p.designator == (key or pr[0].designator)), pr[0])
        b = next((p for p in pn if p.designator == a.designator), pn[0])
        diff_attrs(a, b, f'패드 {a.designator}')
    for tag, f in (('ref', ref), ('new', new)):
        layers = Counter(str(t.layer) for t in f.tracks)
        print(f'  {tag} 트랙 레이어 {dict(layers)}')


def main():
    args = parse_args()
    if args.pcb:
        diff_footprints(load_footprint(*args.ref), load_footprint(*args.new), args.key)
    else:
        diff_symbols(load_symbol(*args.ref), load_symbol(*args.new), args.key)


if __name__ == '__main__':
    main()
