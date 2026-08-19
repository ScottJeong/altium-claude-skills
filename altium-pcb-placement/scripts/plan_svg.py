"""배치 가안 JSON → 1:1 SVG/PNG 도면.

가안은 반드시 **축척 1:1** 이어야 한다. 눈대중 그림은 "들어갈 것 같다" 를 만들고
그건 늘 틀린다. 여기 들어가는 좌표는 그대로 최종 배치 좌표가 된다.

좌표계: 보드 좌하단 원점, mm, +y 는 위. Altium 기본과 같다.

사용:
  python plan_svg.py plan.json -o 배치가안        # .svg / .png 둘 다 생성

plan.json 스키마는 references/plan-schema.md 참조.
"""
import argparse
import json
import os
import sys

# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


try:
    import pymupdf
except ImportError:
    pymupdf = None

SC = 7.0        # px per mm
PAD = 60
NOTE_W = 400


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


class Draw:
    def __init__(self, bw, bh):
        self.bw, self.bh = bw, bh
        self.o = []

    def X(self, v):
        return PAD + v * SC

    def Y(self, v):
        return PAD + (self.bh - v) * SC

    def text(self, x, y, s, size=9, anchor='middle', color='#222', weight='normal'):
        lines = str(s).split('\n')
        y0 = y - (len(lines) - 1) * size * 0.55
        for i, ln in enumerate(lines):
            self.o.append(
                f'<text x="{x:.1f}" y="{y0 + i * size * 1.15:.1f}" font-size="{size}" '
                f'font-family="Malgun Gothic,Arial" text-anchor="{anchor}" '
                f'fill="{color}" font-weight="{weight}">{esc(ln)}</text>')

    def rot_text(self, x, y, s, deg, size=8.5, color='#0a7', weight='normal'):
        self.o.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'font-family="Malgun Gothic,Arial" text-anchor="middle" fill="{color}" '
            f'font-weight="{weight}" transform="rotate({deg} {x:.1f} {y:.1f})">{esc(s)}</text>')


def build(p):
    bw, bh = p['board']['w'], p['board']['h']
    d = Draw(bw, bh)
    W = int(bw * SC + PAD * 2 + NOTE_W)
    H = int(bh * SC + PAD * 2)
    d.o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
               f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#fff"/>')

    for z in p.get('zones', []):
        d.o.append(f'<rect x="{d.X(z["x"]):.1f}" y="{d.Y(z["y"] + z["h"]):.1f}" '
                   f'width="{z["w"] * SC:.1f}" height="{z["h"] * SC:.1f}" '
                   f'fill="{z.get("color", "#eee")}" opacity="0.55"/>')
        lx, ly = z.get('lx', z['x'] + 1), z.get('ly', z['y'] + 1.5)
        d.text(d.X(lx), d.Y(ly), z['name'], 12, 'start', '#777', 'bold')

    d.o.append(f'<rect x="{d.X(0):.1f}" y="{d.Y(bh):.1f}" width="{bw * SC:.1f}" '
               f'height="{bh * SC:.1f}" fill="none" stroke="#000" stroke-width="2.5"/>')
    for g in range(0, int(bw) + 1, 10):
        d.o.append(f'<line x1="{d.X(g):.1f}" y1="{d.Y(0):.1f}" x2="{d.X(g):.1f}" '
                   f'y2="{d.Y(bh):.1f}" stroke="#ddd" stroke-width="0.5"/>')
    for g in range(0, int(bh) + 1, 10):
        d.o.append(f'<line x1="{d.X(0):.1f}" y1="{d.Y(g):.1f}" x2="{d.X(bw):.1f}" '
                   f'y2="{d.Y(g):.1f}" stroke="#ddd" stroke-width="0.5"/>')

    for f in p.get('flows', []):
        (ax, ay), (bx, by) = f['from'], f['to']
        d.o.append(f'<line x1="{d.X(ax):.1f}" y1="{d.Y(ay):.1f}" x2="{d.X(bx):.1f}" '
                   f'y2="{d.Y(by):.1f}" stroke="#c00" stroke-width="2" '
                   f'stroke-dasharray="6 4" opacity="0.75"/>')
        if f.get('label'):
            d.text((d.X(ax) + d.X(bx)) / 2, (d.Y(ay) + d.Y(by)) / 2 - 4,
                   f['label'], 10, 'middle', '#c00', 'bold')

    for b in p.get('tp_banks', []):
        n, dx, dy = b['n'], b.get('dx', 0), b.get('dy', 0)
        for i in range(n):
            d.o.append(f'<circle cx="{d.X(b["x"] + dx * i):.1f}" '
                       f'cy="{d.Y(b["y"] + dy * i):.1f}" r="3.6" fill="#fff" '
                       f'stroke="#0066b3" stroke-width="1.5"/>')
        span = (dx + dy) * (n - 1)
        lab = f'{b.get("name", "TP")} x{n} span {span:.0f}'
        if dy == 0:
            d.text(d.X(b['x'] + dx * (n - 1) / 2),
                   d.Y(b['y']) + (-11 if b['y'] > bh / 2 else 16),
                   lab, 8.5, 'middle', '#0066b3', 'bold')
        else:
            d.rot_text(d.X(b['x']) - 11, d.Y(b['y'] + dy * (n - 1) / 2),
                       lab, -90, 8.5, '#0066b3', 'bold')

    for c in p.get('parts', []):
        x, y, w, h = c['x'], c['y'], c['w'], c['h']
        if c.get('kind') == 'keepout':
            d.o.append(f'<rect x="{d.X(x):.1f}" y="{d.Y(y + h):.1f}" '
                       f'width="{w * SC:.1f}" height="{h * SC:.1f}" fill="none" '
                       f'stroke="#e08000" stroke-width="1.6" stroke-dasharray="8 5"/>')
            d.text(d.X(x + w) - 4, d.Y(y + h) + 13, c.get('label', ''), 9, 'end', '#e08000')
            continue
        d.o.append(f'<rect x="{d.X(x):.1f}" y="{d.Y(y + h):.1f}" width="{w * SC:.1f}" '
                   f'height="{h * SC:.1f}" fill="#fffbe6" stroke="#333" stroke-width="1.6"/>')
        lab = f'{c["des"]}\n{c.get("label", "")}'.rstrip('\n')
        if w * SC < 55 or h * SC < 26:
            d.text(d.X(x + w / 2), d.Y(y) + 12, lab, 8)
        else:
            d.text(d.X(x + w / 2), d.Y(y + h / 2) + 4, lab, 10, 'middle', '#111', 'bold')

    for sk in p.get('socket_sides', []):
        x0, y0, x1, y1 = sk['box']
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for side, lab in sk['labels'].items():
            if side == 'top':
                d.text(d.X(cx), d.Y(y1 - 1.8), lab, 8.5, 'middle', '#0a7')
            elif side == 'bottom':
                d.text(d.X(cx), d.Y(y0 + 1.0), lab, 8.5, 'middle', '#0a7')
            elif side == 'left':
                d.rot_text(d.X(x0 + 2.2), d.Y(cy), lab, -90)
            else:
                d.rot_text(d.X(x1 - 2.0), d.Y(cy), lab, 90)
        if sk.get('pin1'):
            px, py = sk['pin1']
            d.o.append(f'<circle cx="{d.X(px):.1f}" cy="{d.Y(py):.1f}" r="6" fill="#c00"/>')
            d.text(d.X(px) - 18, d.Y(py) + 18, 'P1', 10, 'middle', '#c00', 'bold')

    for hx, hy, hd in [(h['x'], h['y'], h.get('d', 3.2)) for h in p.get('holes', [])]:
        d.o.append(f'<circle cx="{d.X(hx):.1f}" cy="{d.Y(hy):.1f}" '
                   f'r="{hd / 2 * SC:.1f}" fill="none" stroke="#555" stroke-width="1.4"/>')
        d.o.append(f'<circle cx="{d.X(hx):.1f}" cy="{d.Y(hy):.1f}" r="{3.0 * SC:.1f}" '
                   f'fill="none" stroke="#bbb" stroke-width="1" stroke-dasharray="3 3"/>')

    d.o.append(f'<line x1="{d.X(0):.1f}" y1="{d.Y(0) + 26:.1f}" x2="{d.X(bw):.1f}" '
               f'y2="{d.Y(0) + 26:.1f}" stroke="#000" stroke-width="1"/>')
    d.text(d.X(bw / 2), d.Y(0) + 42, f'{bw:g} mm', 13, 'middle', '#000', 'bold')
    my = (d.Y(0) + d.Y(bh)) / 2
    d.rot_text(d.X(0) - 32, my, f'{bh:g} mm', -90, 13, '#000', 'bold')

    d.text(d.X(0), 26, p.get('title', '배치 가안') + '  (Top View, 1:1)', 16, 'start',
           '#000', 'bold')
    d.text(d.X(0), 44, '빨강 점선 = 주요 신호 흐름 / 주황 = 금지구역 / 파랑 원 = 테스트포인트',
           10, 'start', '#666')

    nx = d.X(bw) + 18
    d.text(nx, PAD + 10, 'NOTE', 13, 'start', '#000', 'bold')
    for i, t in enumerate(p.get('notes', [])):
        col = '#c00' if isinstance(t, dict) and t.get('warn') else '#333'
        s = t['text'] if isinstance(t, dict) else t
        d.text(nx, PAD + 32 + i * 22, '· ' + s, 11, 'start', col)

    d.o.append('</svg>')
    return '\n'.join(d.o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan')
    ap.add_argument('-o', '--out', required=True, help='확장자 없는 출력 경로')
    a = ap.parse_args()

    with open(a.plan, encoding='utf-8') as f:
        p = json.load(f)
    svg = build(p)
    with open(a.out + '.svg', 'w', encoding='utf-8') as f:
        f.write(svg)
    if pymupdf is None:
        print('pymupdf 없음 — SVG 만 생성')
        return
    doc = pymupdf.open(stream=svg.encode('utf-8'), filetype='svg')
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2))
    pix.save(a.out + '.png')
    print(f'ok {os.path.basename(a.out)}.svg/.png  {pix.width}x{pix.height}')


if __name__ == '__main__':
    main()
