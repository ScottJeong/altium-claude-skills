"""라이브러리에 뭐가 이미 있는지 훑는다. 새로 만들기 전에 반드시 돌린다.

심볼은 이미 있고 풋프린트만 없는 경우가 흔하다. 그걸 모르고 만들면 중복이 생기고
나중에 어느 게 진짜인지 아무도 모른다.

부품명이 정확히 안 맞을 수 있으니 제조사 약칭·핀수로도 찾아본다.
(부분 문자열 검색. 등록명에 제조사 접두어가 붙어 있는 경우가 많다)

사용:
    python survey_library.py <라이브러리 폴더 또는 파일> [--find 검색어] [--pins 96]
"""

import argparse
import contextlib
import io
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


@contextlib.contextmanager
def quiet():
    """altium_monkey 가 파싱 경고를 stdout 으로 쏟아낸다.

    'SubRecord 5 shorter than expected' 류가 수백 줄 나와서 실제 출력을 덮는다.
    경고는 삼키되, 파싱 실패 자체는 예외로 잡아 따로 표시한다.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', help='.SchLib/.PcbLib 파일 또는 그것들이 든 폴더')
    ap.add_argument('--find', help='이름/설명 부분일치 검색어 (대소문자 무시)')
    ap.add_argument('--pins', type=int, help='이 핀수(패드수)인 것만')
    ap.add_argument('--top', type=int, default=12, help='라이브러리당 출력 개수')
    return ap.parse_args()


def iter_libs(path):
    if os.path.isfile(path):
        yield path
        return
    for root, _dirs, files in os.walk(path):
        for f in sorted(files):
            if f.lower().endswith(('.schlib', '.pcblib')):
                yield os.path.join(root, f)


def survey_sch(path):
    out = []
    try:
        with quiet():
            names = AltiumSchLib.get_symbol_names(path)
            lib = AltiumSchLib(path)
    except Exception as e:
        return [], f'열기 실패: {type(e).__name__}: {e}'
    for n in names:
        try:
            with quiet():
                s = lib.get_symbol(n)
            if s is None:
                continue
            out.append({'name': n, 'count': len(list(s.pins)),
                        'parts': s.part_count,
                        'desc': (s.description or '')[:44],
                        'fp': [i.model_name for i in s.implementations]})
        except Exception as e:
            out.append({'name': n, 'count': -1, 'parts': -1,
                        'desc': f'<파싱실패 {type(e).__name__}>', 'fp': []})
    return out, None


def survey_pcb(path):
    out = []
    try:
        with quiet():
            lib = AltiumPcbLib.from_file(path)
            fps = list(lib.footprints)
    except Exception as e:
        return [], f'열기 실패: {type(e).__name__}: {e}'
    for f in fps:
        try:
            with quiet():
                n_pads = len(list(f.pads))
            out.append({'name': f.name, 'count': n_pads, 'parts': 0,
                        'desc': (getattr(f, 'description', None) or '')[:44], 'fp': []})
        except Exception as e:
            out.append({'name': f.name, 'count': -1, 'parts': 0,
                        'desc': f'<파싱실패 {type(e).__name__}>', 'fp': []})
    return out, None


def main():
    args = parse_args()
    import os
    if not os.path.exists(args.path):
        sys.exit(f'[라이브러리] 경로가 없다: {args.path}')
    q = args.find.lower() if args.find else None
    total = 0
    for lib_path in iter_libs(args.path):
        is_sch = lib_path.lower().endswith('.schlib')
        items, err = (survey_sch if is_sch else survey_pcb)(lib_path)
        if err:
            print(f'--- {os.path.basename(lib_path)}: {err}')
            continue
        sel = items
        if q:
            sel = [i for i in sel
                   if q in i['name'].lower() or q in i['desc'].lower()]
        if args.pins is not None:
            sel = [i for i in sel if i['count'] == args.pins]
        if q or args.pins is not None:
            if not sel:
                continue
        sel = sorted(sel, key=lambda i: -i['count'])[:args.top]
        kind = '심볼' if is_sch else '풋프린트'
        print(f'\n--- {os.path.basename(lib_path)}  ({kind} {len(items)}개)')
        for i in sel:
            unit = 'pins' if is_sch else 'pads'
            extra = f' parts={i["parts"]}' if is_sch else ''
            fp = f'  fp={i["fp"]}' if i['fp'] else ('  fp=없음' if is_sch else '')
            print(f'   {unit}={i["count"]:4d}{extra}  {i["name"]:38s} {i["desc"]}{fp}')
            total += 1
    if q and total == 0:
        print(f'\n{args.find!r} 로는 아무것도 못 찾았다. '
              '제조사 약칭이나 핀수(--pins)로도 찾아보라.')
    print(f'\n찾은 항목 {total}개')
    print('심볼에 fp=없음 이면 풋프린트 링크가 안 붙어 있다는 뜻이다.')


if __name__ == '__main__':
    main()
