"""회로도 → 부품쌍 연결 매트릭스 + 기준부품 핀별 상대 + TP 소속.

배치의 근거는 "누가 누구와 몇 넷으로 붙어 있나" 다. 그것부터 뽑는다.
전원 레일(팬아웃이 큰 넷)은 배치 근거가 못 되므로 --rail-fanout 이상은 뺀다.

넷 구성은 altium-schematic-review 스킬의 net_erc.build 를 그대로 쓴다.
(멀티파트 파트 필터·hidden 핀·핀-핀 직결이 이미 들어가 있다. 다시 짜지 마라.)
"""
import argparse
import collections
import itertools
import os
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


try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SIBLING = os.path.normpath(os.path.join(HERE, '..', '..',
                                        'altium-schematic-review', 'scripts'))


def load_net_erc():
    if SIBLING not in sys.path:
        sys.path.insert(0, SIBLING)
    try:
        import net_erc
    except ImportError:
        sys.exit(f'net_erc.py 없음: {SIBLING}\n'
                 'altium-schematic-review 스킬이 설치돼 있어야 한다.')
    return net_erc


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('schdoc')
    ap.add_argument('--ref', help='기준 부품 지정자 (예: U2). 핀별 상대를 뽑는다')
    ap.add_argument('--rail-fanout', type=int, default=8,
                    help='이 개수 넘게 붙은 넷은 전원 레일로 보고 제외 (기본 8)')
    ap.add_argument('--tp-prefix', default='TP')
    return ap.parse_args()


def main():
    a = parse_args()
    _need(a.schdoc, 'SchDoc')
    N = load_net_erc()
    with N.quiet():
        nets, _comps = N.build(a.schdoc)

    pair = collections.Counter()
    tp_owner = collections.defaultdict(set)
    ref_rows = []
    rails = 0

    for v in nets.values():
        pins = [p for p in v['pins'] if p['desig']]
        desigs = sorted({p['desig'] for p in pins})
        if len(desigs) > a.rail_fanout:
            rails += 1
            continue
        real = [d for d in desigs if not d.startswith(a.tp_prefix)]
        for x, y in itertools.combinations(sorted(set(real)), 2):
            pair[(x, y)] += 1
        for d in desigs:
            if d.startswith(a.tp_prefix):
                for x in real:
                    tp_owner[x].add(d)
        if a.ref:
            mine = [p for p in pins if p['desig'] == a.ref]
            if mine:
                others = [d for d in real if d != a.ref]
                name = ','.join(sorted(v['names'])) or '-'
                for p in mine:
                    key = int(p['pin']) if str(p['pin']).isdigit() else 10 ** 6
                    ref_rows.append((key, p['pin'], p['name'], name, others))

    print(f'=== 넷 {len(nets)}개 (전원 레일로 제외 {rails}개, 팬아웃>{a.rail_fanout})')

    print('\n=== 부품쌍 넷 수 — 이게 존 분할의 1차 근거')
    for (x, y), n in pair.most_common(40):
        print(f'  {x:<6} {y:<6} {n}')

    print(f'\n=== {a.tp_prefix} 소속 (테스트포인트를 어느 부품 옆에 둘지)')
    for k, v in sorted(tp_owner.items(), key=lambda kv: -len(kv[1])):
        print(f'  {k:<6} {len(v)}')

    if a.ref:
        print(f'\n=== {a.ref} 핀별 상대 — 회전 결정 입력값')
        print('  (핀번호 · 핀이름 · 넷 · 상대부품)')
        for _k, pin, pname, net, others in sorted(ref_rows):
            print(f'  {str(pin):>4}  {pname:<16} {net[:20]:<20} {",".join(others)}')


if __name__ == '__main__':
    main()
