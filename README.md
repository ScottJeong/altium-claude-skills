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

## 파이썬

스크립트는 [`altium_monkey`](https://github.com/wavenumber-eng/altium_monkey) 를 쓴다.
이 패키지가 Python `<3.13` 을 요구하므로 **3.12 가상환경**을 따로 판다.

```powershell
py -3.12 -m venv C:\tools\edatools
C:\tools\edatools\Scripts\pip install altium-monkey pymupdf
```

스킬 본문에서 이 인터프리터를 `python` 이라고 부른다. 스크립트를 돌릴 때
**그 venv 의 python.exe** 로 실행한다.

일부 스크립트는 `altium-mcp` MCP 서버도 쓴다 (Altium 을 켠 채 조작). 없으면
파일 파싱 기능만 동작한다.

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
