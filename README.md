# altium-claude-skills

Altium 하드웨어 설계용 Claude Code 스킬. **다른 사람이 받아 쓸 수 있게** 만든다.

| 스킬 | 하는 일 |
|---|---|
| `altium-library` | 심볼(.SchLib)·풋프린트(.PcbLib) 를 코드로 만들고 검증. 데이터시트·2D 도면 실측 포함 |
| `altium-schematic-review` | 회로도(.SchDoc) 검토 — 미결선·풋프린트 누락·넷 오류를 찾고 데이터시트로 판정 |
| `altium-pcb-placement` | PCB 배치 — 보드 사이즈 역산, 주요 IC·커넥터 회전 결정, 배치 가안 도면, 좌표 투입, 겹침 검사 |

## 설치

이 폴더가 실제 원본이고, `~/.claude/skills/` 에는 **디렉터리 정션**만 건다.
심볼릭 링크가 아니라 정션이라 관리자 권한이 필요 없고, 클라우드 동기화 쪽에서는
평범한 폴더로만 보인다.

```powershell
$repo = "C:\path\to\altium-claude-skills"   # clone 한 위치
foreach ($s in 'altium-library','altium-pcb-placement','altium-schematic-review') {
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\$s" -Target "$repo\$s"
}
```

새 PC 라면 `$repo` 를 그 PC 의 경로로 바꾼다. 정션은 절대경로를 굽는다.

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

**`eda-agent` 는 쓰지 않는다.** Altium 안에 자체 폴링 루프를 띄워야 하는데
**Altium 의 스크립팅 슬롯이 전역으로 하나**라, 그걸 띄우면 `altium-mcp` 브릿지가 죽는다.
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

## 배포용이라 넣지 않는 것

- **프로젝트 고유 정보.** 칩·보드 이름, 그 설계값, 사내 부품 번호.
  실증은 남기되 **주체를 익명화**한다 — 교훈은 그대로 남고 정보는 안 샌다.
  시판 부품(데이터시트 공개)은 그대로 써도 된다
- **사내 경로·개인 절대경로.** 남의 PC 에서 전부 깨진다
- **개인 작업 방식과 내 환경 전제.** → [`claude-skills-personal`](https://github.com/letjsk/claude-skills-personal)

## 규칙

- 스킬을 고칠 때는 **왜 고쳤는지 근거를 본문에 남긴다.** 함정은 겪은 사례와 같이 적는다
- 스크립트를 프로젝트 폴더로 복사해 쓰지 않는다. 사본이 갈라지면 고친 게 반영 안 된 판이 돌아간다
- 스킬 폴더 안에서 파이썬을 돌리면 `__pycache__`·`.omc` 가 생긴다. `.gitignore` 에 있다
