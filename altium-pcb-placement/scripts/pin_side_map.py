"""기준 부품의 핀번호 → 변(side) 매핑, 회전 4안 비교.

배치에서 사람이 제일 자주 틀리는 게 "이 IC 를 몇 도로 놓을까" 다.
근거는 취향이 아니라 **어느 신호 무리가 어느 변에서 나오는가** 하나뿐이다.
QFN/QFP 는 핀번호가 변을 결정하므로 순수하게 계산된다.

입력
  --pins-per-side  한 변당 핀 수 (68핀 4변이면 17)
  --start          핀1 이 있는 변 (left/bottom/right/top)
  --dir            번호 진행 방향 (ccw 기본, QFN 표준)
  --group          "이름=핀목록"  예: --group "BUS_A=1-10,55-64"
  --want           "그룹=방향"    예: --want "BUS_A=NE"  (선택, 점수용)

출력
  회전 0/90/180/270 각각에 대해 그룹이 어느 변·어느 방향으로 나오는지.
  방향은 그룹 핀들의 변 단위벡터 평균이다 → 코너에 몰리면 대각 방향이 나온다.

**핀1 위치와 진행 방향은 반드시 본드 도면/패키지 도면으로 확인하고 넣는다.**
추정하면 결과 전체가 뒤집힌다.
"""
import argparse
import math
import sys

# Windows 콘솔은 cp949 라 —, ✓ 에서 죽는다. 콘솔 코드페이지와 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

SIDES = ['left', 'bottom', 'right', 'top']
VEC = {'left': (-1, 0), 'bottom': (0, -1), 'right': (1, 0), 'top': (0, 1)}
KO = {'left': '좌', 'bottom': '하', 'right': '우', 'top': '상'}
COMPASS = [('E', '우'), ('NE', '우상'), ('N', '상'), ('NW', '좌상'),
           ('W', '좌'), ('SW', '좌하'), ('S', '하'), ('SE', '우하')]


def parse_pins(spec):
    out = []
    for chunk in spec.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if '-' in chunk:
            a, b = chunk.split('-')
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(chunk))
    return out


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pins-per-side', type=int, required=True)
    ap.add_argument('--start', default='left', choices=SIDES)
    ap.add_argument('--dir', default='ccw', choices=['ccw', 'cw'])
    ap.add_argument('--group', action='append', default=[],
                    help='이름=핀목록 (예: BUS_A=1-10,55-64)')
    ap.add_argument('--want', action='append', default=[],
                    help='이름=방향 (E/NE/N/NW/W/SW/S/SE)')
    return ap.parse_args()


def side_order(start, direction):
    """핀 번호가 커질 때 지나는 변 순서."""
    i = SIDES.index(start)
    seq = [SIDES[(i + k) % 4] for k in range(4)]     # ccw: left→bottom→right→top
    if direction == 'cw':
        seq = [SIDES[(i - k) % 4] for k in range(4)]
    return seq


def compass(vx, vy):
    if abs(vx) < 1e-9 and abs(vy) < 1e-9:
        return '-', '사방'
    ang = math.degrees(math.atan2(vy, vx)) % 360
    idx = int((ang + 22.5) // 45) % 8
    return COMPASS[idx]


def main():
    a = parse_args()
    order = side_order(a.start, a.dir)

    groups = {}
    for g in a.group:
        name, spec = g.split('=', 1)
        groups[name.strip()] = parse_pins(spec)
    wants = {}
    for w in a.want:
        name, d = w.split('=', 1)
        wants[name.strip()] = d.strip().upper()

    def base_side(pin):
        return order[((pin - 1) // a.pins_per_side) % 4]

    print(f'0° 기준 변 배정 — 핀1={a.start}, 진행={a.dir}, 변당 {a.pins_per_side}핀')
    for k, sd in enumerate(order):
        lo = k * a.pins_per_side + 1
        hi = (k + 1) * a.pins_per_side
        print(f'  P{lo}~P{hi}  →  {sd} ({KO[sd]})')

    # 회전 r(도, CCW) 만큼 돌리면 변 인덱스가 r/90 만큼 CCW 로 간다.
    print('\n=== 회전 비교 (Altium rotation = 반시계 도)')
    best = None
    for rot in (0, 90, 180, 270):
        k = rot // 90
        print(f'\n--- rotation {rot}°' + (f'  (= CW {360 - rot}°)' if rot else ''))
        score = 0
        for name, pins in groups.items():
            hist = {}
            vx = vy = 0.0
            for p in pins:
                sd = base_side(p)
                sd2 = SIDES[(SIDES.index(sd) + k) % 4]
                hist[sd2] = hist.get(sd2, 0) + 1
                dx, dy = VEC[sd2]
                vx += dx
                vy += dy
            n = max(1, len(pins))
            vx, vy = vx / n, vy / n
            c_en, c_ko = compass(vx, vy)
            spread = ', '.join(f'{KO[s]}{hist[s]}' for s in SIDES if s in hist)
            mark = ''
            if name in wants:
                if wants[name] == c_en:
                    score += 2
                    mark = '  ✓'
                elif wants[name] in c_en or c_en in wants[name]:
                    score += 1
                    mark = '  ~'
            print(f'  {name:<10} → {c_ko:<3}({c_en:<2})  [{spread}]{mark}')
        if wants:
            print(f'  점수 {score}')
            if best is None or score > best[1]:
                best = (rot, score)

    if best:
        print(f'\n권고: rotation {best[0]}°  (점수 {best[1]})')
    print('\n※ 코너로 나온 그룹(NE/NW/SE/SW)은 그 대각 방향에 상대 부품을 놓으면 교차가 0 이 된다.')


if __name__ == '__main__':
    main()
