# altium-claude-skills

[English](README.md) | 한국어

Altium 하드웨어 설계를 Claude Code 로 하기 위한 스킬 모음.
심볼·풋프린트 제작, 회로도 검토, PCB 배치 세 단계를 다룬다.

실제 보드 한 장(부품 175개)을 회로도 검토부터 배치까지 끌고 가며 만들었다.
겪은 함정을 사례와 함께 본문에 남겨 뒀다.

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

### 1. Altium Designer

Windows. 파일 파싱만 하는 기능은 Altium 없이도 되지만, 배치·스크린샷·라이브러리
조회는 Altium 이 떠 있어야 한다.

### 2. 파이썬 + `altium_monkey`

스크립트 대부분이 [`altium_monkey`](https://github.com/wavenumber-eng/altium_monkey)
로 Altium 파일(`.SchDoc` `.PcbDoc` `.PcbLib` `.SchLib`)을 **직접 파싱**한다.
Altium 을 안 켜도 되는 게 장점이다.

이 패키지가 Python `<3.13` 을 요구하므로 **3.12 가상환경**을 따로 판다.

```powershell
py -3.12 -m venv C:\tools\edatools
C:\tools\edatools\Scripts\pip install altium-monkey pymupdf
```

스킬 본문에서 이 인터프리터를 `python` 이라고 부른다. **그 venv 의 python.exe** 로 돌린다.

`pymupdf` 는 데이터시트·2D 도면에서 치수를 재는 데 쓴다 (벤더 도면은 문자가
텍스트가 아니라 벡터 아웃라인이라 렌더해서 읽어야 한다).

### 3. MCP 서버

| MCP | 쓰는 곳 | 없으면 |
|---|---|---|
| [`altium-mcp`](https://github.com/coffeenmusic/altium-mcp) | **배치**(`place_components`), 스크린샷, 라이브러리 심볼/풋프린트 조회, 열려 있는 보드 상태 읽기 | `altium-pcb-placement` 의 좌표 투입과 육안 검증이 안 된다. 나머지(파일 파싱·계산·가안 도면)는 동작 |
| `pcbparts` | 부품 사양·재고(`jlc_search`), 일반 설계 규칙(`get_design_rules`) | 판정 근거를 데이터시트·웹에서 직접 찾으면 된다. 선택 |

`WebSearch` / `WebFetch` 는 데이터시트를 못 찾을 때 쓴다 (Claude Code 기본 도구).

**`eda-agent` 를 `altium-mcp` 와 동시에 띄우지 마라.** Altium 안에 자체 폴링 루프를 띄워야 하는데
**Altium 의 스크립팅 슬롯이 전역으로 하나**라, 그걸 띄우면 `altium-mcp` 브릿지가 죽는다.
`altium-library` 의 3D 모델 절에 `eda-agent` 도구를 쓰는 **선택 단계**가 둘 있다
(`lib_extract_cse_zip`, `lib_easyeda_import`). 그 단계만 쓰려면 `altium-mcp` 를 내리고
`eda-agent` 를 띄운 뒤 끝나면 되돌린다. 없어도 수동으로 대체된다.

같은 이유로 `altium-mcp` 의 `run_altium_script` 도 꼭 필요할 때만 쓴다 —
런타임 에러가 나면 스크립트가 디버거에 멈춰 **모든 MCP 도구가 막히고 사람이
`Ctrl+F3` 을 눌러야** 풀린다.

### 4. 없어도 되는 것

3D 모델을 받아 붙이는 절이 있는데 여기서만 외부 소스를 쓴다
(KiCad packages3D, EasyEDA). 인터넷만 되면 별도 설치는 없다.

## 무엇이 Altium 없이 되나

| | Altium 필요 | 파일만 |
|---|---|---|
| 라이브러리 제작·검증 | 육안 확인 | 생성·비교·측정 |
| 회로도 검토 | 컴파일 넷 대조(선택) | 넷 구성·ERC 유사 검사·풋프린트 대조 |
| PCB 배치 | **좌표 투입**·스크린샷 | 치수 실측·회전 계산·가안 도면·겹침 검사 |

**외주 PCB 설계업체에 넘길 배치 가안은 Altium 없이도 만들 수 있다.**
회로도와 라이브러리(또는 데이터시트)만 있으면 된다.

## 고칠 때

- **규칙으로 쓰고, 근거는 검증된 숫자로 붙인다.** 겪은 사례를 서사로 적지 않는다.
  `QFN32 몸체 4.00 → 실제 풋프린트 7.05×7.00` 은 정보고,
  「내가 4×4 로 잡았다가 틀렸다」 는 남의 일지다. 같은 걸 알려주면서 앞쪽만 남긴다
- **스크립트를 프로젝트 폴더로 복사해 쓰지 않는다.** 사본이 갈라지면
  고친 게 반영 안 된 판이 계속 돌아간다
- **특정 칩·보드 이름과 그 설계값을 넣지 않는다.** 범용 스킬이다.
  판정은 그때그때 데이터시트를 보고 한다

## 라이선스

[MIT](LICENSE)
