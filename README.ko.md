# altium-claude-skills

[English](README.md) | 한국어

Altium 하드웨어 설계를 Claude Code 로 하기 위한 스킬 모음.
심볼·풋프린트 제작, 회로도 검토, PCB 배치 세 단계를 다룬다.

실제 보드 한 장(부품 175개)을 회로도 검토부터 배치까지 끌고 가며 썼다.
그래서 여기 적힌 함정은 실제로 걸리는 것들이고, 전부 **규칙 + 실측 숫자** 형태로 적혀 있다.

| 스킬 | 하는 일 |
|---|---|
| `altium-library` | 심볼(.SchLib)·풋프린트(.PcbLib) 를 코드로 만들고 검증. 데이터시트·2D 도면 실측 포함 |
| `altium-schematic-review` | 회로도(.SchDoc) 검토 — 미결선·풋프린트 누락·넷 오류를 찾고 데이터시트로 판정 |
| `altium-pcb-placement` | PCB 배치 — 보드 사이즈 역산, 주요 IC·커넥터 회전 결정, 배치 가안 도면, 좌표 투입, 겹침 검사 |

## 설치

clone 한 뒤 `~/.claude/skills/` 에 **디렉터리 정션**을 건다.
정션은 심볼릭 링크와 달리 관리자 권한이 필요 없다.

```powershell
git clone https://github.com/letjsk/altium-claude-skills.git `
    C:\path\to\altium-claude-skills

$repo = "C:\path\to\altium-claude-skills"
foreach ($s in 'altium-library','altium-pcb-placement','altium-schematic-review') {
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\$s" -Target "$repo\$s"
}
```

**정션은 절대경로를 굽는다.** repo 를 옮기면 정션을 다시 만들어야 한다.
정션이 싫으면 세 폴더를 `~/.claude/skills/` 로 그냥 복사해도 된다 —
대신 `git pull` 한 게 자동으로 반영되지 않는다.

## 스킬 사이 의존

`altium-pcb-placement` 의 `connectivity_matrix.py` 는 `altium-schematic-review` 의
`net_erc.py` 를 가져다 쓴다 (형제 폴더 상대경로). **둘을 같이 설치해야 한다.**

## 필요한 것

### Altium Designer

Windows. 파일만 읽는 단계는 Altium 을 안 켜도 된다. 배치·스크린샷·라이브 조회는 켜야 한다.

### Python 3.12 + `altium_monkey`

스크립트 대부분이 Altium 파일(`.SchDoc` `.PcbDoc` `.PcbLib` `.SchLib`)을
[`altium_monkey`](https://github.com/wavenumber-eng/altium_monkey) 로 **직접 파싱**한다.
그래서 Altium 이 안 떠 있어도 된다. 이 패키지가 Python `<3.13` 을 요구한다.

```powershell
# 1. Python 3.12 가 없으면 설치하고, 이 용도로 venv 를 판다
py -3.12 -m venv C:\tools\edatools

# 2. 패키지 둘
C:\tools\edatools\Scripts\python.exe -m pip install altium-monkey pymupdf

# 3. 확인
C:\tools\edatools\Scripts\python.exe -c "import altium_monkey, pymupdf; print('ok')"
```

스크립트는 **그 venv 의 `python.exe` 를 전체 경로로** 부른다. 스킬 본문은 이걸 `python`
이라고만 쓰니, PATH 의 `python` 이 그것이라고 가정하지 마라.

`pymupdf` 는 데이터시트·2D 도면 실측용이다. 벤더 도면은 문자가 벡터 아웃라인이라
텍스트 추출이 안 되고 렌더해서 읽어야 한다.

### MCP: `altium-mcp`

떠 있는 Altium 을 조작한다. **배치**(`place_components`)·스크린샷·라이브 라이브러리
조회에 필요하다. 없으면 파일만 만지는 것은 전부 그대로 된다 — 파싱·실측·회전 계산·
가안 도면·겹침 검사.

```powershell
git clone https://github.com/coffeenmusic/altium-mcp.git C:\tools\altium-mcp

claude mcp add altium-mcp --scope user -- `
    C:\tools\edatools\Scripts\python.exe C:\tools\altium-mcp\start_server.py
```

서버가 첫 호출 때 자기 venv 를 부트스트랩하고 Altium 에 스크립트 프로젝트를 설치한다.
`claude mcp list` 로 등록을 보고, Claude 에게 `get_server_status` 를 시켜 확인한다.

> 그쪽 README 는 Claude **Desktop** 방식(`.dxt` 확장)만 적혀 있다.
> Claude **Code** 는 위처럼 `claude mcp add` 로 붙인다.

### MCP: `pcbparts` (선택)

부품 사양·재고(`jlc_search`), 일반 설계 규칙(`get_design_rules`). 호스팅이라 설치 없다.

```powershell
claude mcp add --transport http pcbparts --scope user https://pcbparts.dev/mcp
```

없으면 데이터시트나 웹(`WebSearch`/`WebFetch`, Claude Code 기본 도구)에서 같은 걸 찾으면 된다.

### `eda-agent` 를 `altium-mcp` 와 같이 띄우지 마라

**Altium 의 스크립팅 슬롯은 전역으로 하나다.** `eda-agent` 는 Altium 안에 자체 폴링
루프를 띄워야 해서, 그걸 시작하면 `altium-mcp` 브릿지가 죽는다.

`altium-library` 의 3D 모델 절에 `eda-agent` 도구를 쓰는 **선택 단계**가 둘 있다
(`lib_extract_cse_zip`, `lib_easyeda_import`). 그 단계만 쓰려면 `altium-mcp` 를 내리고
`eda-agent` 를 띄운 뒤 되돌린다. 둘 다 수동 대체가 있다.

같은 이유로 `run_altium_script` 는 꼭 필요할 때만 쓴다 — 런타임 에러가 나면 스크립트가
Altium 디버거에 멈춰 **모든 MCP 도구가 막히고** 사람이 `Ctrl+F3` 을 눌러야 풀린다.

## 무엇이 Altium 없이 되나

| | Altium 필요 | 파일만 |
|---|---|---|
| 라이브러리 제작·검증 | 육안 확인 | 생성·비교·측정 |
| 회로도 검토 | 컴파일 넷 대조(선택) | 넷 구성·ERC 유사 검사·풋프린트 대조 |
| PCB 배치 | **좌표 투입**·스크린샷 | 치수 실측·회전 계산·가안 도면·겹침 검사 |

**외주 PCB 설계업체에 넘길 배치 가안은 Altium 없이도 만들 수 있다.**
회로도와 라이브러리(또는 데이터시트)만 있으면 된다.

## 기여

이슈·PR 환영. 두 가지만 지키면 계속 쓸 만하다.

- **규칙으로 쓰고 실측 숫자로 뒷받침한다.** 사고 경위를 서술하지 않는다.
  `QFN32 몸체 4.00 → 실제 풋프린트 7.05×7.00` 이 정보다
- **특정 칩·보드 이름과 한 설계의 값을 넣지 않는다.** 범용 스킬이고,
  판정은 그때그때 데이터시트로 한다

## 라이선스

[MIT](LICENSE)
