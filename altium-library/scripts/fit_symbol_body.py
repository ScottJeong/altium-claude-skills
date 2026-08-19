"""심볼 본체 최소 크기를 겹침 검사로 계산한다.

핀 이름은 본체 **안쪽**으로 들어온다. 상/하 핀의 이름은 90도 돌아 세로로 들어온다.
그래서 본체가 작으면 이름끼리 겹치는데, **좌표 검산으로도 SVG 렌더로도 안 잡힌다**
(SVG 렌더러는 세로 이름을 안 돌려서 항상 겹쳐 보인다).

어림잡으면 두 번 틀린다:
  1. 변마다 최장 이름만큼만 여백  -> 여백이 제각각이라 핀 블록이 쏠린다. 칩처럼 안 보임
  2. 네 변을 지배값으로 통일      -> 대칭은 맞는데 과하게 커진다

실제 제약은 "이름끼리 안 겹치면 된다" 뿐이고, 좌/우 이름과 상/하 이름은 서로 다른
영역이라 **부딪치는 건 코너뿐**이다. 그래서 전수 교차검사로 최소치를 찾는다.

빌드 스크립트에서 import 해서 쓰는 게 정석이다:

    from fit_symbol_body import min_square_body
    W = H = min_square_body(LEFT, RIGHT, TOP, BOTTOM, extra_left=['GND'])

크기를 상수로 박지 마라. 핀 이름을 고치면 본체가 자동으로 다시 잡혀야 한다.

CLI:
    python fit_symbol_body.py sides.json
    echo '{"left":["ISET",...],"right":[...],"top":[...],"bottom":[...]}' | python fit_symbol_body.py -
"""

from __future__ import annotations

import json
import os
import sys

# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# --- 글자 지표 (Times New Roman, Altium 기본 폰트) --------------------------
# symbol_to_svg() 출력에서 실측한 값이다. 본체 rect 폭(SVG unit)과 알려진 본체 폭(mil)
# 으로 스케일을 잡으면 나온다. 32핀 QFN 심볼에서 1 unit = 10 mil 로 측정:
#     "RXDV/CRS_DV/FX_HEN" 18자 = 998 mil  -> 55.4 mil/자
#     "RXCLK/50M_CLKO"     14자 = 793 mil  -> 56.6 mil/자
#     font-size 90 mil
# 새 부품에서 폰트가 다르면 같은 방법으로 다시 재라. 눈대중 금지.
CHAR_W = 60.0     # 실측 56.6 + 여유
TEXT_H = 90.0     # font-size
EDGE_OFF = 50.0   # 본체 엣지 ~ 이름 시작
CLEAR = 40.0      # 이름 상자끼리 최소 이격
PITCH = 100.0     # 핀 피치


def _boxes(size, left, right, top, bottom, extra_left, extra_bottom):
    """각 핀 이름 텍스트의 본체 안쪽 bbox. (side, x1, y1, x2, y2, name)

    8핀 블록(= 인자로 받은 네 리스트)을 각 변 **정중앙**에 정렬한다.
    extra_* 는 그 변 끝에 이어 붙인다 (exposed pad 처럼 변에 속하지 않는 핀).
    """
    row0 = -(size - PITCH * (len(left) - 1)) / 2
    col0 = (size - PITCH * (len(top) - 1)) / 2
    bs = []
    for i, nm in enumerate(list(left) + list(extra_left)):
        y = row0 - PITCH * i
        bs.append(('L', EDGE_OFF, y - TEXT_H / 2, EDGE_OFF + len(nm) * CHAR_W, y + TEXT_H / 2, nm))
    for i, nm in enumerate(right):
        y = row0 - PITCH * i
        bs.append(('R', size - EDGE_OFF - len(nm) * CHAR_W, y - TEXT_H / 2, size - EDGE_OFF, y + TEXT_H / 2, nm))
    for i, nm in enumerate(top):
        x = col0 + PITCH * i
        bs.append(('T', x - TEXT_H / 2, -EDGE_OFF - len(nm) * CHAR_W, x + TEXT_H / 2, -EDGE_OFF, nm))
    for i, nm in enumerate(list(bottom) + list(extra_bottom)):
        x = col0 + PITCH * i
        bs.append(('B', x - TEXT_H / 2, -size + EDGE_OFF, x + TEXT_H / 2, -size + EDGE_OFF + len(nm) * CHAR_W, nm))
    return bs


def overlaps(size, left, right, top, bottom, extra_left=(), extra_bottom=()):
    """다른 변 이름끼리의 충돌 + 본체 밖으로 나간 것을 돌려준다.

    **같은 변끼리는 검사하지 않는다.** 100mil 피치로 고정이고 그건 항상 성립한다
    (텍스트 bbox 높이가 피치보다 커서 검사하면 전부 충돌로 잡힌다).
    """
    bs = _boxes(size, left, right, top, bottom, extra_left, extra_bottom)
    bad = []
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            if a[0] == b[0]:
                continue
            if (a[1] < b[3] + CLEAR and b[1] < a[3] + CLEAR
                    and a[2] < b[4] + CLEAR and b[2] < a[4] + CLEAR):
                bad.append(f'{a[0]}:{a[5]} x {b[0]}:{b[5]}')
    for s, x1, y1, x2, y2, nm in bs:
        if x1 < 0 or x2 > size or y2 > 0 or y1 < -size:
            bad.append(f'{s}:{nm} 본체밖')
    return bad


def min_square_body(left, right, top, bottom, extra_left=(), extra_bottom=(),
                    lo=400, hi=6000, step=100, verbose=False):
    """겹침 없는 최소 정사각 본체 크기(mil). 못 찾으면 ValueError."""
    for size in range(lo, hi + 1, step):
        if not overlaps(size, left, right, top, bottom, extra_left, extra_bottom):
            if verbose:
                prev = overlaps(size - step, left, right, top, bottom, extra_left, extra_bottom)
                print(f'본체 {size} x {size} mil')
                print(f'  한 단계 아래 {size - step} 충돌 {len(prev)}건: {prev[:3]}')
            return size
    raise ValueError(f'{hi} 까지 겹침 없는 크기를 못 찾았다. 이름이 너무 길거나 핀이 너무 많다')


def _main(argv):
    if len(argv) == 2 and argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 1
    if argv[1] != '-' and not os.path.isfile(argv[1]):
        print(f'[핀정의 JSON] 파일이 없다: {argv[1]}')
        return 1
    src = sys.stdin.read() if argv[1] == '-' else open(argv[1], encoding='utf-8').read()
    d = json.loads(src)
    size = min_square_body(
        d['left'], d['right'], d['top'], d['bottom'],
        d.get('extra_left', []), d.get('extra_bottom', []), verbose=True)
    print(f'\n권장: W = H = {size}')
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
