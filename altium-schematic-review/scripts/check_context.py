"""§0 전제 확인 — 검토를 시작하기 전에 헛수고를 막는다.

가장 흔한 사고: Altium 이 켜져 있고 사용자가 저장을 안 했는데 디스크 파일을 읽어
"전원부가 없다", "애너테이션이 안 됐다" 같은 결론을 내는 것. 실제로 그렇게 두 번 틀렸다.

사용:
    python check_context.py <프로젝트폴더 또는 .SchDoc> [--datasheets <폴더>]
"""
import argparse
import contextlib
import io
import os
import subprocess
from collections import Counter
from datetime import datetime
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


try:
    from altium_monkey import AltiumSchDoc
except ImportError:
    raise SystemExit('altium_monkey 없음. edatools venv 파이썬으로 실행하라.')


@contextlib.contextmanager
def quiet():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def walk(o):
    for ch in getattr(o, 'children', []) or []:
        yield ch
        yield from walk(ch)


def altium_running():
    try:
        out = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq X2.EXE', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=20).stdout
        return 'X2.EXE' in out
    except Exception:
        return None


def find_schdocs(path):
    if os.path.isfile(path):
        return [path]
    out = []
    for root, _d, files in os.walk(path):
        for f in files:
            if f.lower().endswith('.schdoc'):
                out.append(os.path.join(root, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target')
    ap.add_argument('--datasheets', help='데이터시트 폴더 (없으면 자동 탐색)')
    args = ap.parse_args()
    import os
    if not os.path.exists(args.target):
        sys.exit(f'[대상] 경로가 없다: {args.target}')

    schdocs = find_schdocs(args.target)
    if not schdocs:
        raise SystemExit(f'.SchDoc 을 못 찾았다: {args.target}')

    run = altium_running()
    print('=== Altium 실행 여부')
    if run is None:
        print('  판단 불가')
    elif run:
        print('  **실행 중**')
        print('  → 메모리가 최신이고 디스크가 구판일 수 있다.')
        print('  → 아래 수정시각이 방금 작업한 내용을 담고 있는지 사용자에게 확인할 것.')
        print('  → 확인 없이 "미구현", "안 돼 있다" 라고 말하지 마라.')
    else:
        print('  꺼져 있음 (디스크 파일이 곧 현재 상태)')

    print('\n=== 회로도 파일')
    now = datetime.now()
    for p in schdocs:
        st = os.stat(p)
        mt = datetime.fromtimestamp(st.st_mtime)
        age = now - mt
        mins = int(age.total_seconds() // 60)
        flag = '  ← 최근 변경' if mins < 30 else ''
        print(f'  {os.path.basename(p):40s} {st.st_size:9,d} B  '
              f'{mt:%Y-%m-%d %H:%M}  ({mins}분 전){flag}')

    for p in schdocs:
        print(f'\n=== 내용: {os.path.basename(p)}')
        try:
            with quiet():
                d = AltiumSchDoc(p)
                comps = list(d.components)
                ports = list(d.get_power_ports())
                labels = list(d.get_net_labels())
                wires = list(d.get_wires())
        except Exception as e:
            print(f'  열기 실패: {type(e).__name__}: {e}')
            continue
        un = 0
        pre = Counter()
        for c in comps:
            t = next((str(getattr(ch, 'text', '')) for ch in walk(c)
                      if type(ch).__name__ == 'AltiumSchDesignator'), '?')
            if '?' in t:
                un += 1
            pre[''.join(ch for ch in t if ch.isalpha()) or '?'] += 1
        print(f'  부품 {len(comps)} / 배선 {len(wires)} / '
              f'전원포트 {len(ports)} / 넷라벨 {len(labels)}')
        print(f'  지정자 접두: {dict(pre.most_common(12))}')
        if un:
            print(f'  **애너테이션 미완: {un}/{len(comps)}**')
            print('   → 내 파이썬 검사는 그대로 된다.')
            print('   → 다만 보고에 부품 이름을 못 쓰고, Altium ECO/ERC 는 막힌다.')
            if run:
                print('   → Altium 이 켜져 있다. 메모리에는 되어 있고 저장만 안 됐을 수 있다.')
        else:
            print('  애너테이션 완료')
        print(f'  전원포트 종류: {dict(Counter(str(getattr(x, "text", "")) for x in ports).most_common())}')

    print('\n=== 데이터시트 (판정 근거로 쓸 것)')
    ds = args.datasheets
    if not ds:
        base = args.target if os.path.isdir(args.target) else os.path.dirname(args.target)
        for _ in range(4):
            cand = [os.path.join(base, n) for n in os.listdir(base)
                    if os.path.isdir(os.path.join(base, n))
                    and 'data' in n.lower() and 'sheet' in n.lower()]
            if cand:
                ds = cand[0]
                break
            nb = os.path.dirname(base)
            if nb == base:
                break
            base = nb
    if ds and os.path.isdir(ds):
        pdfs = [f for f in os.listdir(ds) if f.lower().endswith('.pdf')]
        print(f'  {ds}')
        for f in sorted(pdfs)[:25]:
            print(f'     {f}')
        if len(pdfs) > 25:
            print(f'     … 외 {len(pdfs) - 25}개')
    else:
        print('  못 찾음. 판정 때 웹에서 받아야 한다 (WebSearch -> WebFetch -> pymupdf)')


if __name__ == '__main__':
    main()
