"""회로도 부품의 풋프린트 링크를 뽑고, 실물이 있는 라이브러리와 대조한다.

PCB 로 넘어가기 전에 "풋프린트가 없는 부품" 을 미리 잡는 용도.
Altium 을 켜지 않고 altium_monkey 로 파일을 직접 읽는다.

한계 — Altium 은 설치 라이브러리·통합 라이브러리(.IntLib)·검색 경로로 풋프린트를 찾는다.
여기서는 --libs 로 준 폴더의 .PcbLib 만 본다. 그 밖에 있으면 '없음' 으로 잘못 나온다.
"""

import argparse
import collections
import contextlib
import io
import os
import sys

# Windows 콘솔 기본 코드페이지(cp949 등)로는 −·✓ 같은 문자를 못 찍어 죽는다.
# 콘솔 설정과 무관하게 utf-8 로 낸다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


try:
    from altium_monkey import AltiumPcbLib, AltiumSchDoc
except ImportError:
    sys.exit('altium_monkey 없음. edatools venv 파이썬으로 실행하라.')


@contextlib.contextmanager
def quiet():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('schdoc')
    ap.add_argument('--libs', nargs='+', required=True)
    return ap.parse_args()


def walk_children(obj):
    for ch in getattr(obj, 'children', []) or []:
        yield ch
        yield from walk_children(ch)


def comp_info(c):
    desig, models = None, []
    for ch in walk_children(c):
        t = type(ch).__name__
        if t == 'AltiumSchDesignator' and desig is None:
            desig = getattr(ch, 'text', None)
        elif t == 'AltiumSchImplementation':
            mt = (getattr(ch, 'model_type', '') or '').upper()
            mn = getattr(ch, 'model_name', '') or ''
            if mn and mt in ('PCBLIB', 'PCB', ''):
                models.append(mn)
    return desig or '?', models


def collect_library_footprints(dirs):
    fps, libs, broken = {}, [], []
    for d in dirs:
        if not os.path.isdir(d):
            print(f'  [경고] 폴더 없음: {d}')
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith('.pcblib'):
                    libs.append(os.path.join(root, f))
    for path in sorted(libs):
        try:
            with quiet():
                lib = AltiumPcbLib.from_file(path)
                names = [fp.name for fp in lib.footprints]
        except Exception as e:
            broken.append((os.path.basename(path), type(e).__name__))
            continue
        for n in names:
            fps.setdefault(n.strip().lower(), []).append((os.path.basename(path), n))
    return fps, libs, broken


def main():
    args = parse_args()

    print('=== 라이브러리 수집')
    fps, libs, broken = collect_library_footprints(args.libs)
    print(f'  .PcbLib {len(libs)}개, 풋프린트 이름 {len(fps)}종')
    for b, e in broken:
        print(f'  [경고] {b} 열기 실패 ({e}) — 이 라이브러리 내용은 대조 못 함')

    print(f'\n=== 회로도: {os.path.basename(args.schdoc)}')
    with quiet():
        doc = AltiumSchDoc(args.schdoc)
        comps = list(doc.components)
    # 멀티파트 심볼은 파트 수만큼 컴포넌트 레코드가 나온다(J1-A/B/C 처럼).
    # 지정자로 접어야 개수가 BOM 과 맞는다. 지정자 미할당(?)은 접을 수 없으니 그대로 둔다.
    seen_desig = set()
    parts_total = len(comps)
    print(f'  파트 인스턴스 {parts_total}개')

    no_link, missing, ok = [], [], []
    unannotated = []
    for c in comps:
        desig, models = comp_info(c)
        libref = c.lib_reference or c.design_item_id or '<이름없음>'
        if '?' not in str(desig):
            if desig in seen_desig:
                continue          # 같은 부품의 다른 파트
            seen_desig.add(desig)
        if '?' in str(desig):
            unannotated.append((desig, libref))
        if not models:
            no_link.append((desig, libref))
            continue
        for mn in models:
            hit = fps.get(mn.strip().lower())
            rec = (desig, libref, mn, hit[0][0] if hit else None)
            (ok if hit else missing).append(rec)

    print('\n=== 결과')
    folded = parts_total - len(seen_desig) - len(unannotated)
    if folded > 0:
        print(f'  멀티파트로 접은 레코드   : {folded} (지정자 {len(seen_desig)}개로 집계)')
    print(f'  링크 있고 실물 확인됨    : {len(ok)}')
    print(f'  링크 있는데 실물 못 찾음 : {len(missing)}')
    print(f'  링크 자체가 없음         : {len(no_link)}')
    print(f'  지정자 미할당(?)         : {len(unannotated)}')

    if no_link:
        print(f'\n--- [A] 풋프린트 링크 없음 ({len(no_link)}개)')
        for desig, lr in sorted(no_link):
            print(f'  {desig:10s} {lr}')

    if missing:
        print(f'\n--- [B] 링크는 있는데 라이브러리에 없음')
        by_fp = collections.defaultdict(list)
        for desig, lr, mn, _ in missing:
            by_fp[mn].append((desig, lr))
        for mn, items in sorted(by_fp.items(), key=lambda kv: -len(kv[1])):
            refs = sorted({lr for _d, lr in items})
            print(f'  {mn:38s} x{len(items):3d}  심볼={", ".join(refs[:3])}')
            print(f'      {", ".join(sorted(d for d, _ in items)[:14])}'
                  + (' …' if len(items) > 14 else ''))

    print('\n--- [C] 확인된 풋프린트')
    by_fp = collections.defaultdict(lambda: [0, None])
    for desig, lr, mn, lib in ok:
        by_fp[mn][0] += 1
        by_fp[mn][1] = lib
    for mn, (n, lib) in sorted(by_fp.items()):
        print(f'  {mn:38s} x{n:3d}  <- {lib}')


if __name__ == '__main__':
    main()
