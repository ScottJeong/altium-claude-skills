"""벤더 2D 도면 PDF 에서 홀 좌표와 외곽선을 벡터로 실측한다.

도면 문자는 벡터 아웃라인이라 텍스트 추출이 안 되고, 렌더 이미지 픽셀 눈대중은 틀린다.
그래서 도형 좌표를 직접 뽑고 **이미 아는 피치로 pt/mm 스케일을 역산**한다.

사용:
    # 1) 먼저 전체를 렌더해서 어느 영역인지 정한다
    python measure_drawing.py drawing.pdf --render whole.png

    # 2) 영역을 페이지 비율로 잘라 홀을 잰다
    python measure_drawing.py drawing.pdf --clip 0.55 0.03 0.95 0.36 --pitch 2.54

    # 3) 외곽선이 필요하면 선분도 굵기별로 덤프
    python measure_drawing.py drawing.pdf --clip 0.03 0.32 0.62 0.60 --pitch 2.54 --lines

반드시 검산할 것: 출력된 홀 지름이 도면에 적힌 값과 1% 안에 드는지.
안 맞으면 스케일이 틀렸거나 다른 뷰를 재고 있는 것이다.
"""

import argparse
import sys
from collections import Counter, defaultdict

# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


try:
    import pymupdf
except ImportError:  # pragma: no cover
    sys.exit("pymupdf 가 없다:  uv pip install --python <venv python> pymupdf")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf')
    ap.add_argument('--page', type=int, default=0)
    ap.add_argument('--clip', nargs=4, type=float, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='페이지 비율로 자를 영역 (0~1)')
    ap.add_argument('--pitch', type=float,
                    help='스케일 역산에 쓸 알려진 행 간격 (mm). 없으면 pt 로만 출력')
    ap.add_argument('--render', metavar='PNG', help='해당 영역을 PNG 로 저장')
    ap.add_argument('--dpi', type=int, default=400)
    ap.add_argument('--lines', action='store_true', help='선분을 굵기별로 덤프')
    ap.add_argument('--min-line-mm', type=float, default=2.0,
                    help='--lines 에서 이 길이 이상만 출력 (mm, 스케일 없으면 pt)')
    return ap.parse_args()


def collect_circles(page, clip):
    """가로세로가 거의 같은 작은 닫힌 경로를 원으로 본다.

    도면의 원은 곡선(item 'c')이 아니라 폴리라인 근사인 경우가 많아
    item 종류로 찾으면 하나도 안 잡힌다. bbox 모양으로 판정한다.
    """
    found = {}
    for path in page.get_drawings():
        r = path['rect']
        if clip and not clip.intersects(r):
            continue
        w, h = r.width, r.height
        if w < 0.5 or h < 0.5 or w > 60 or h > 60:
            continue
        if abs(w - h) > 0.12 * max(w, h):
            continue
        if len(path['items']) < 6:
            continue
        found[(round(r.x0 + w / 2, 1), round(r.y0 + h / 2, 1))] = (w + h) / 2
    return [(cx, cy, d) for (cx, cy), d in found.items()]


def group(vals, tol):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1][-1] > tol:
            out.append([v])
        else:
            out[-1].append(v)
    return [sum(g) / len(g) for g in out]


def collect_lines(page, clip):
    hor, ver = [], []
    for path in page.get_drawings():
        lw = path.get('width')
        dashed = path.get('dashes') not in (None, '', '[] 0')
        for it in path['items']:
            if it[0] != 'l':
                continue
            a, b = it[1], it[2]
            if clip and not (clip.contains(a) and clip.contains(b)):
                continue
            if abs(a.y - b.y) < 0.05 and abs(a.x - b.x) > 0.3:
                hor.append((round(a.y, 2), round(min(a.x, b.x), 2),
                            round(max(a.x, b.x), 2), lw, dashed))
            elif abs(a.x - b.x) < 0.05 and abs(a.y - b.y) > 0.3:
                ver.append((round(a.x, 2), round(min(a.y, b.y), 2),
                            round(max(a.y, b.y), 2), lw, dashed))
    return sorted(set(hor)), sorted(set(ver))


def main():
    args = parse_args()
    doc = pymupdf.open(args.pdf)
    page = doc[args.page]
    W, H = page.rect.width, page.rect.height
    clip = None
    if args.clip:
        x0, y0, x1, y1 = args.clip
        clip = pymupdf.Rect(x0 * W, y0 * H, x1 * W, y1 * H)
    print(f'page {W:.1f} x {H:.1f} pt   clip={clip}')

    if args.render:
        page.get_pixmap(clip=clip, dpi=args.dpi).save(args.render)
        print(f'wrote {args.render}')

    kinds = Counter()
    for p in page.get_drawings():
        for it in p['items']:
            kinds[it[0]] += 1
    print(f'draw item kinds: {dict(kinds)}   '
          f"(곡선 'c' 가 없으면 원이 폴리라인 근사다)")

    circles = collect_circles(page, clip)
    if not circles:
        print('\n원으로 볼 만한 경로가 없다. --clip 을 확인하라.')
    else:
        diam = Counter(round(d, 1) for _, _, d in circles)
        print(f'\n지름 히스토그램 (pt): {diam.most_common(8)}')
        small_d = diam.most_common(1)[0][0]
        small = [c for c in circles if abs(c[2] - small_d) < 0.4]
        big = [c for c in circles if c[2] > small_d * 2.0]
        print(f'작은 원 {len(small)}개 / 큰 원 {len(big)}개')

        rows = group([cy for _, cy, _ in small], 1.0)
        cols = group([cx for cx, _, _ in small], 1.0)
        print(f'행 {len(rows)}개 y(pt): {[round(v, 2) for v in rows]}')
        print(f'열 {len(cols)}개')

        scale = None
        if args.pitch and len(rows) > 1:
            gaps = [rows[i + 1] - rows[i] for i in range(len(rows) - 1)]
            scale = sum(gaps) / len(gaps) / args.pitch
            print(f'행 간격(pt) {[round(g, 3) for g in gaps]}'
                  f'  ->  {scale:.4f} pt/mm')
            print(f'  [검산] 작은 원 O = {small_d / scale:.3f} mm')
            for _, _, d in big:
                print(f'  [검산] 큰 원   O = {d / scale:.3f} mm')
            print('  도면에 적힌 값과 1% 안에 안 들면 스케일이 틀린 것이다.')

        if big and rows:
            print('\n큰 원(마운팅홀) 위치 — 각 행 기준:')
            for cx, cy, d in sorted(big):
                parts = []
                for i, ry in enumerate(rows):
                    dy = (cy - ry) / scale if scale else (cy - ry)
                    parts.append(f'row{i}:{dy:+.3f}')
                print(f'  x={cx:8.2f}  ' + '  '.join(parts))

    if args.lines:
        hor, ver = collect_lines(page, clip)
        scale = None
        if args.pitch and circles:
            rows = group([cy for _, cy, _ in collect_circles(page, clip)], 1.0)
            if len(rows) > 1:
                gaps = [rows[i + 1] - rows[i] for i in range(len(rows) - 1)]
                scale = sum(gaps) / len(gaps) / args.pitch
        unit = 'mm' if scale else 'pt'

        def conv(v):
            return v / scale if scale else v

        widths = Counter(round(w, 3) for *_, w, _ in hor if w)
        print(f'\n선 굵기 히스토그램: {widths.most_common(6)}')
        print('  굵은 쪽이 부품 외곽, 얇은 쪽이 치수 보조선이다. 굵은 것만 보라.')
        print('  [주의] 아래 len 은 세로 스케일로 환산한 값이다. 뷰에 break(~) 가 있으면')
        print('         그 방향 축척이 깨져 있어 가로 길이는 믿으면 안 된다.')
        print('         쓸 수 있는 건 좌표(y 위치)와 굵기다.')

        by_w = defaultdict(list)
        for y, a, b, lw, dash in hor:
            if conv(b - a) >= args.min_line_mm and not dash:
                by_w[round(lw or 0, 3)].append((y, a, b))
        print(f'\n--- 수평 실선 (길이 >= {args.min_line_mm}{unit}) ---')
        for lw in sorted(by_w, reverse=True):
            print(f'  lw={lw}')
            for y, a, b in sorted(by_w[lw]):
                print(f'    y={y:8.2f}  x {a:8.2f}..{b:8.2f}  len={conv(b - a):7.2f}{unit}')

        by_w = defaultdict(list)
        for x, a, b, lw, dash in ver:
            if conv(b - a) >= args.min_line_mm and not dash:
                by_w[round(lw or 0, 3)].append((x, a, b))
        print(f'\n--- 수직 실선 (길이 >= {args.min_line_mm}{unit}) ---')
        for lw in sorted(by_w, reverse=True):
            print(f'  lw={lw}')
            for x, a, b in sorted(by_w[lw]):
                print(f'    x={x:8.2f}  y {a:8.2f}..{b:8.2f}  len={conv(b - a):7.2f}{unit}')


if __name__ == '__main__':
    main()
