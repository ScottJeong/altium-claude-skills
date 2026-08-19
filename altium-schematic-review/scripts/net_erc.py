"""회로도 넷 구성 + ERC 유사 검사 (Altium 없이).

trace_net.py 의 후속. 이전 판은 '배선 위에 있는 핀' 만 넷에 넣어서
Altium 컴파일 결과(182넷)보다 훨씬 적은 105넷만 잡았다. 빠진 77개는
핀-핀 직결 / 핀-전원포트 직결 / hidden 핀이었다.

이번 판이 추가로 처리하는 것
  - 좌표가 같은 단자끼리 연결 (핀-핀, 핀-포트, 핀-라벨 직결)
  - 배선에 안 닿는 단자도 독립 넷으로 유지 (버리지 않는다)
  - hidden 핀은 핀 이름으로 자동 연결 (Altium 이 그렇게 한다)

그 위에 ERC 유사 검사 4종을 얹는다.
"""
import argparse
import contextlib
import io
import re
from collections import Counter, defaultdict

from altium_monkey import AltiumSchDoc
import sys

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


# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


TOL = 5
ELEC = {0: 'Input', 1: 'IO', 2: 'Output', 3: 'OpenCollector', 4: 'Passive',
        5: 'HiZ', 6: 'OpenEmitter', 7: 'Power'}
DRIVERS = {'Output', 'Power'}          # 넷을 구동한다고 보는 타입
SOFT_DRIVERS = {'IO', 'OpenCollector', 'OpenEmitter', 'HiZ', 'Passive'}


@contextlib.contextmanager
def quiet():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def walk(o):
    for ch in getattr(o, 'children', []) or []:
        yield ch
        yield from walk(ch)


def xy(p):
    if p is None:
        return None
    if isinstance(p, (tuple, list)) and len(p) >= 2:
        return (p[0], p[1])
    if hasattr(p, 'x') and hasattr(p, 'y'):
        return (p.x, p.y)
    return xy(getattr(p, 'location', None))


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def part_of(comp):
    """이 컴포넌트 레코드가 몇 번 파트인지. 단일파트면 None."""
    try:
        pid = int(getattr(comp, 'current_part_id', None))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def pin_in_part(pin, part_id):
    """이 핀이 이 파트 소속인가.

    멀티파트 심볼은 파트 레코드마다 **전체 핀**을 들고 있고,
    `get_pin_hotspot` 은 파트를 안 가리고 designator 로만 찾는다.
    그래서 걸러내지 않으면 A1/B1/C1 이 같은 좌표로 나와 서로 다른 넷이
    하나로 합쳐진다 — 3V3↔5V 같은 **가짜 단락**이 생긴다.
    (실측: 96핀 DIN 커넥터 심볼 3파트짜리에서 확인)

    핀의 `owner_part_id` 는 정상이다. 0 이하이거나 없으면 모든 파트 공용으로 본다.
    """
    if part_id is None:
        return True
    try:
        owner = int(getattr(pin, 'owner_part_id', None))
    except (TypeError, ValueError):
        return True
    return owner <= 0 or owner == part_id


def on_seg(pt, a, b):
    (x, y), (x1, y1), (x2, y2) = pt, a, b
    if min(x1, x2) - TOL <= x <= max(x1, x2) + TOL and \
       min(y1, y2) - TOL <= y <= max(y1, y2) + TOL:
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        span = max(abs(x2 - x1), abs(y2 - y1), 1)
        return abs(cross) <= TOL * span
    return False


def build(path):
    with quiet():
        d = AltiumSchDoc(path)
        comps = list(d.components)
        wires = list(d.get_wires())
        ports = list(d.get_power_ports())
        labels = list(d.get_net_labels())

    segs = []
    for w in wires:
        cs = [xy(v) for v in (getattr(w, 'points', None) or [])]
        cs = [(c[0] * 10, c[1] * 10) for c in cs if c]
        for a, b in zip(cs, cs[1:]):
            segs.append((a, b))

    dsu = DSU()
    for i in range(len(segs)):
        dsu.find(('S', i))
    for i, (a1, b1) in enumerate(segs):
        for j in range(i + 1, len(segs)):
            a2, b2 = segs[j]
            if (on_seg(a1, a2, b2) or on_seg(b1, a2, b2)
                    or on_seg(a2, a1, b1) or on_seg(b2, a1, b1)):
                dsu.union(('S', i), ('S', j))

    # --- 단자 수집 -------------------------------------------------------
    terms = []          # (key, 좌표, 종류, 정보)
    dropped = 0
    for ci, c in enumerate(comps):
        desig = next((str(getattr(ch, 'text', '')) for ch in walk(c)
                      if type(ch).__name__ == 'AltiumSchDesignator'), '?')
        part_id = part_of(c)
        for ch in walk(c):
            if type(ch).__name__ != 'AltiumSchPin':
                continue
            if not pin_in_part(ch, part_id):
                dropped += 1
                continue
            pd = str(ch.designator)
            try:
                pt = tuple(c.get_pin_hotspot(pd))
            except Exception:
                continue
            info = {'ci': ci, 'desig': desig, 'lib': str(c.lib_reference),
                    'pin': pd, 'name': str(ch.name), 'part': part_id,
                    'elec': ch.electrical_name, 'hidden': bool(ch.is_hidden)}
            terms.append((('P', ci, pd), pt, 'pin', info))
    if dropped:
        print(f'# 멀티파트: 다른 파트 소속 핀 {dropped}개 제외')
    for i, p in enumerate(ports):
        pt = xy(p)
        if pt:
            terms.append((('W', i), (pt[0] * 10, pt[1] * 10), 'port',
                          {'text': str(getattr(p, 'text', ''))}))
    for i, lb in enumerate(labels):
        pt = xy(lb)
        if pt:
            terms.append((('L', i), (pt[0] * 10, pt[1] * 10), 'label',
                          {'text': str(getattr(lb, 'text', ''))}))

    # 단자 <-> 배선
    for key, pt, kind, info in terms:
        dsu.find(key)
        for i, (a, b) in enumerate(segs):
            if on_seg(pt, a, b):
                dsu.union(key, ('S', i))

    # 좌표가 같은 단자끼리 (핀-핀 직결, 핀-포트 직결)
    bucket = defaultdict(list)
    for key, pt, kind, info in terms:
        bucket[(round(pt[0] / TOL), round(pt[1] / TOL))].append(key)
    for keys in bucket.values():
        for k in keys[1:]:
            dsu.union(keys[0], k)

    # --- 넷 조립 ---------------------------------------------------------
    nets = defaultdict(lambda: {'pins': [], 'names': set()})
    for key, pt, kind, info in terms:
        r = dsu.find(key)
        if kind == 'pin':
            nets[r]['pins'].append(info)
        else:
            if info['text']:
                nets[r]['names'].add(info['text'])

    # 이름으로 합치기 + hidden 핀은 핀 이름으로 합류
    name_dsu = DSU()
    by_name = defaultdict(list)
    for r, v in nets.items():
        name_dsu.find(r)
        for n in v['names']:
            by_name[n].append(r)
    for r, v in nets.items():
        for p in v['pins']:
            if p['hidden'] and p['name']:
                by_name[p['name']].append(r)
    for n, rs in by_name.items():
        for r in rs[1:]:
            name_dsu.union(rs[0], r)

    merged = defaultdict(lambda: {'pins': [], 'names': set()})
    for r, v in nets.items():
        k = name_dsu.find(r)
        merged[k]['pins'] += v['pins']
        merged[k]['names'] |= v['names']
    return merged, comps


def erc(nets):
    out = defaultdict(list)
    for k, v in nets.items():
        pins = v['pins']
        nm = sorted(v['names']) or ['(무명)']
        if not pins:
            continue
        elec = Counter(p['elec'] for p in pins)
        real = [p for p in pins if not p['hidden']]

        if len(pins) == 1:
            out['단일핀'].append((nm, pins))
        outs = elec.get('Output', 0) + elec.get('Power', 0)
        if outs >= 2 and not (v['names'] & {'GND', '3V3', '5V', 'IP_3V3',
                                            'IP_3V3A', 'VDD33IO'}):
            out['출력충돌'].append((nm, [p for p in pins
                                      if p['elec'] in DRIVERS]))
        if elec and set(elec) <= {'Input'}:
            out['구동원없음'].append((nm, pins))
        if len(real) >= 2 and not v['names']:
            out['무명넷'].append((nm, pins))
    return out


def near_dupe_names(nets):
    names = sorted({n for v in nets.values() for n in v['names']})
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a == b:
                continue
            if len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1:
                pairs.append((a, b))
            else:
                ra = re.sub(r'\d+', '#', a)
                rb = re.sub(r'\d+', '#', b)
                if ra == rb and abs(len(a) - len(b)) <= 1 and a[:3] == b[:3]:
                    pass
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('schdoc')
    ap.add_argument('--net')
    ap.add_argument('--limit', type=int, default=12)
    args = ap.parse_args()
    _need(args.schdoc, 'SchDoc')

    nets, comps = build(args.schdoc)
    withpins = {k: v for k, v in nets.items() if v['pins']}
    desigs = {next((str(getattr(ch, 'text', '')) for ch in walk(c)
                    if type(ch).__name__ == 'AltiumSchDesignator'), '?')
              for c in comps}
    print(f'파트 인스턴스 {len(comps)} / 지정자 {len(desigs)}개 '
          f'/ 넷(핀 있는 것) {len(withpins)}')
    print('  ※ 멀티파트 부품은 파트 수만큼 인스턴스로 잡힌다. BOM 수량은 지정자 쪽이다')

    if args.net:
        for k, v in withpins.items():
            if any(args.net.upper() == n.upper() for n in v['names']):
                print(f'\n=== {sorted(v["names"])}  핀 {len(v["pins"])}')
                for p in sorted(v['pins'], key=lambda z: (z['desig'], z['pin'])):
                    print(f'   {p["desig"]:8s} {p["lib"]:24s} 핀 {p["pin"]:>5s} '
                          f'{p["name"]:18s} {p["elec"]:14s} hidden={p["hidden"]}')
        return

    res = erc(withpins)
    # 단일핀·출력충돌·구동원없음은 **한 건씩 판정해야 하는 후보 목록**이라 자르지 않는다.
    # 자르면 도구를 돌려놓고 후보를 못 본 것과 같아진다.
    NO_LIMIT = {'단일핀', '출력충돌', '구동원없음'}
    for tag in ('단일핀', '출력충돌', '구동원없음', '무명넷'):
        items = res.get(tag, [])
        lim = len(items) if tag in NO_LIMIT else args.limit
        print(f'\n=== {tag}: {len(items)}건')
        for nm, pins in items[:lim]:
            print(f'  {nm}')
            for p in pins[:6]:
                print(f'     {p["desig"]:8s} {p["lib"]:22s} 핀 {p["pin"]:>5s} '
                      f'{p["name"]:16s} {p["elec"]}')
        if len(items) > lim:
            print(f'  … 외 {len(items) - lim}건 (--limit 로 늘린다)')

    dup = near_dupe_names(withpins)
    print(f'\n=== 한 글자만 다른 넷 이름: {len(dup)}쌍')
    for a, b in dup[:20]:
        print(f'   {a}   <->   {b}')


if __name__ == '__main__':
    main()
