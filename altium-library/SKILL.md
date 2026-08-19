---
name: altium-library
description: Create and verify Altium schematic symbols (.SchLib) and PCB footprints (.PcbLib) from datasheets and 2D drawings, as code. Use whenever a part library must be made, fixed, measured from a drawing, or checked. Triggers: "make a footprint", "create a symbol", "add this part to the library", "SchLib", "PcbLib", "footprint", "schematic symbol", "pad coordinates", "pin mapping", "verify this library", or being handed a component drawing and asked to turn it into a library — even if Altium is not named. 한국어: Altium 심볼(.SchLib)·풋프린트(.PcbLib) 라이브러리를 코드로 만들고 검증하는 절차. "풋프린트 만들어", "심볼 만들어", "라이브러리 추가", "커넥터/IC 라이브러리", "패드 좌표", "핀 배치", "Altium 라이브러리 검증", 부품 도면을 주면서 "이거 라이브러리로 만들어줘" 라고 하면 이 스킬이다. 검증만 요청받은 경우에도 쓴다.
---

# Altium 라이브러리 제작·검증

라이브러리는 한 번에 맞지 않는다. **틀리는 지점이 정해져 있어서** 그걸 순서로 막는 게 핵심이다.
아래 순서는 실제로 10건의 결함이 난 세션에서 역산한 것이다.
잡히는 결함과 안 잡히는 결함이 갈렸다:

- 숫자·기준파일과 대조 가능한 것 → 검산으로 잡힌다
- **그 물건이 물리적으로 뭔지**, **툴이 어떻게 그리는지** → 검산으로 안 잡힌다. 그래서 §2 와 §6 이 있다

## 0. 도구 분담 — 이건 안 바뀐다

| 하는 일 | 도구 |
|---|---|
| **생성·수정** | `altium_monkey` (파이썬). Altium 없이 파일을 직접 쓴다 |
| **검증·조회** | `altium-mcp` MCP. **읽기 전용으로만** |

`altium-mcp` 의 `create_schematic_symbol` / `create_pcb_footprint` 는 **실행 중인 Altium 의
활성 문서에 직접 쓴다.** 사용자가 열어둔 남의 라이브러리를 오염시킬 수 있고, 어느 문서가
활성인지 확실히 보장할 방법이 없다. 생성에 쓰지 마라.

파이썬은 반드시 이 인터프리터:

```
python
```

3.12 venv 다. `altium-monkey` 가 `Requires-Python <3.13` 이라 시스템 3.13 에는 안 깔린다.
패키지 추가는 `uv pip install --python <위 경로> <패키지>` (venv 에 pip 가 없다).

## 작업 폴더 — 부품 하나 = 폴더 하나

산출물과 중간물을 한 폴더에 몰면 부품 두세 개만 늘어도 뭐가 뭔지 못 찾는다.
(실제로 커넥터 하나에 파일 29개가 평평하게 쌓였다.)

```
<작업폴더>\
├── index.md            부품 목록·상태·공용 라이브러리 반영 여부
└── <MPN>/              폴더명은 MPN. 괄호·슬래시 등 경로에 나쁜 문자는 뺀다
    ├── build.py        생성 코드. 근거와 판단 이유가 주석에 — 이게 진실이다
    ├── out/            산출물(.PcbLib/.SchLib). 공용 라이브러리로 옮기는 건 여기서만
    ├── work/           도면 렌더, 측정 기록(measure-commands.md), 일회용 스크립트(adhoc/)
    └── check/          검증용 사본(_chk, _v2 …). 언제든 지워도 되는 것
```

- `build.py` 는 `OUT = Path(__file__).parent / "out"` 로 쓴다
- **도면에서 잰 명령과 중간 결과를 `work/measure-commands.md` 에 남긴다.**
  clip 좌표·스케일·검산값이 없으면 나중에 재현이 안 된다
- 일회용 분석 스크립트를 부품 폴더마다 복제하지 마라. 범용화해서 이 스킬의
  `scripts/` 로 올리고, 부품 폴더에는 **쓴 명령만** 기록한다
- 새 부품을 끝내면 `index.md` 에 한 줄 추가한다 (산출물·상태·공용 반영 여부·미해결)

## 1. 이미 있는지 먼저 본다

새로 만들기 전에 **기존 라이브러리를 검색한다.** 심볼은 이미 있고 풋프린트만 없는 경우가 흔하다.

라이브러리 폴더 경로는 환경마다 다르다. 프로젝트 폴더 → Altium 워크스페이스
(`%APPDATA%\Altium\Altium Designer {GUID}\LastWorkspace\*.DsnWrk` 안에 `.LibPkg`
절대경로가 그대로 있다) → **사용자에게 묻는다** 순으로 찾는다.

```
python scripts/survey_library.py <라이브러리 폴더 또는 .PcbLib/.SchLib>
python scripts/survey_library.py <폴더> --find PCN10      # 부분 문자열
python scripts/survey_library.py <폴더> --pins 96         # 핀 수로
```

부품명이 정확히 안 맞을 수 있으니 **제조사 약칭·핀수로도** 찾아본다 —
등록명에 제조사 접두어가 붙어 있는 경우가 많다.

있으면 **그걸 쓰고 없는 쪽만 만든다.** 겹치게 만들면 나중에 어느 게 진짜인지 아무도 모른다.

## 2. 기준 부품을 잡고 전면 diff — 이 단계를 건너뛰면 나중에 다 터진다

같은 라이브러리에서 **같은 종류의 부품 하나**를 기준으로 잡는다 (커넥터면 커넥터, QFN 이면 QFN).
그리고 **속성만 비교하지 말고 원시 레코드까지** 비교한다.

```
python scripts/diff_symbol.py --ref <기준.SchLib> <기준심볼명> --new <내.SchLib> <내심볼명>
```

이 스크립트가 3층으로 비교한다:

1. **파싱된 속성** — 좌표, 길이, 방향, 전기타입
2. **레코드 순서** — z-order 가 여기서 결정된다 (§6 참조)
3. **원시 바이트** — 플래그 비트까지

속성만 비교하면 "일치" 라고 나오는데 화면은 딴판일 수 있다. 실제로 그랬다.
색·z-order·핀번호 표시가 전부 1·2층에서는 안 보이고 2·3층에서 나왔다.

기준 부품에서 반드시 가져올 것:

- 본체 사각형 **색** (`color` 테두리 / `area_color` 채움). 기본값을 쓰면 기존 심볼과 눈에 띄게 다르다
- **레코드 순서** (사각형이 핀보다 앞인가 뒤인가)
- 핀 **길이·피치·x 위치**, 지정자/파라미터 위치
- 핀 플래그 바이트

## 3. 심볼 핀 배치 — 패키지 순서가 기본, 기능 그룹은 물어본다

**기본값은 데이터시트 탑뷰 도면 그대로다.** 회로도만 보고 칩의 어느 변 몇 번째 핀인지
알 수 있어야 브링업·프로빙이 된다.

기능 그룹(입력 좌 / 출력 우 / 전원 위 / GND 아래)으로 재배치하는 건
**사용자에게 물어보고 나서** 한다. 마음대로 바꾸지 마라.
(업계 다수는 기능 그룹이고 KiCad KLC S4.2 · Altium 공식 가이드도 그쪽이다.
그래도 이 사용자의 기본값은 패키지 순서다. 관례를 근거로 임의로 뒤집지 마라.)

물어봐야 하는 신호:

- 핀이 많아 한 변에 안 들어가거나 멀티파트가 필요할 때
- 같은 버스가 여러 변에 흩어져 회로도 배선이 꼬일 때
- 공용 라이브러리가 그 부품군을 기능 그룹으로 관리하고 있을 때

### 도면의 시작 코너까지 맞춰라

"패키지 순서" 는 **번호 도는 방향(보통 반시계)만 맞추는 게 아니다.**
1번핀이 **어느 코너에서 시작하는지**까지 맞춰야 도면과 겹쳐 보인다.

**시작 코너를 데이터시트에서 확인하고 맞춘다.**
탑뷰 1번핀이 좌하단인데 심볼은 좌변 위부터 놓으면, 반시계 순서가 같아
전기적으로는 문제없지만 **도면 대비 90° 돌아간다.**
"칩과 같은 위치라 찾기 쉽다" 는 목적이 절반만 달성된다.

**도면을 렌더해서 눈으로 확인해라.** 텍스트 추출만으로는 상/하 변 라벨이
회전 텍스트라 안 잡힌다 (좌/우 변만 읽힌다).

### 변에 속하지 않는 핀 (exposed pad 등)

**번호가 이어지는 변 끝에 붙인다.** 32 다음이면 좌변 32 아래.
그 변만 한 핀 길어지는데 그게 오히려 "네 변에 속하지 않는 핀" 표시가 된다.
멀리 떨어뜨려 놓으면 찾기 나쁘다.

### 본체 크기는 계산한다 — 어림잡으면 두 번 틀린다

핀 이름은 본체 **안쪽**으로 들어온다. 상/하 핀의 이름은 90° 돌아 세로로 들어온다.

어림잡아 틀린 순서 (실제로 두 번 지적받았다):

1. 변마다 최장 이름만큼만 여백 → 여백이 제각각이라 핀 블록이 쏠린다. **칩처럼 안 보인다**
2. 네 변을 지배값으로 통일 → 대칭은 맞는데 **과하게 커진다**

실제 제약은 **"이름끼리 안 겹치면 된다"** 뿐이다. 좌/우 이름과 상/하 이름은
서로 다른 영역이라 대부분 만나지도 않는다 — **부딪치는 건 코너뿐이다.**

```
python scripts/fit_symbol_body.py sides.json
```

빌드 스크립트에 import 해서 쓰는 게 정석이다:

```python
from fit_symbol_body import min_square_body
W = H = min_square_body(LEFT, RIGHT, TOP, BOTTOM, extra_left=['GND'])
```

- 같은 변끼리는 100mil 피치 고정 → **검사 대상이 아니다**
  (텍스트 높이가 피치보다 커서 검사하면 전부 충돌로 잡힌다)
- 8핀 블록 4개를 각 변 정중앙에 정렬 → 대칭
- **크기를 상수로 박지 마라.** 핀 이름을 고치면 본체가 자동으로 다시 잡혀야 한다

글자 지표는 **실측한다.** `symbol_to_svg()` 출력에서 본체 rect 폭(SVG unit)과
알려진 본체 폭(mil)으로 스케일을 잡으면 문자 폭이 바로 나온다.
측정값 (Times New Roman, Altium 기본): **약 56 mil/자**, font-size **90 mil**.
여유 둬서 `CHAR_W=60` `TEXT_H=90` 이격 40 으로 잡는다.

어림과 계산의 차이는 크다 — 32핀·최장 이름 18자에서
2700 정사각(어림) → **2300 정사각(계산)**, 면적 27% 감소.

### 상/하 핀 이름은 렌더로 검증할 수 없다

`symbol_to_svg()` 렌더러는 **세로 핀 이름을 안 돌린다.** 가로로 그려서 겹쳐 보이는데
Altium 에서는 안 겹친다. **기준 심볼도 똑같이 겹쳐 보인다** — 그걸로 아티팩트인지 확인해라.
상/하 이름 판정은 위 겹침 계산으로 한다.

## 4. 도면은 벡터로 잰다 — 픽셀 눈대중은 전부 틀린다

벤더 2D 도면(Hirose 등)은 **문자가 텍스트가 아니라 벡터 아웃라인**이다.
PDF 텍스트 추출이 통째로 실패한다 (워터마크만 나온다).

**렌더한 이미지를 눈으로 재지 마라.** 렌더 스케일 → 표시 스케일 이중 변환에서
오차가 쌓이고 선 굵기 때문에 경계가 밀린다. 거리는 반드시 벡터로 잰다.

대신 **도형 좌표를 뽑고 이미 아는 치수로 스케일을 역산**한다:

```
python scripts/measure_drawing.py <도면.pdf> --clip 0.55 0.03 0.95 0.36 --pitch 2.54
```

- 원(홀)의 bbox 중심을 모아 행/열을 찾는다
- 알려진 피치(핀 간격)로 `pt/mm` 을 역산한다
- **검산**: 도면에 적힌 다른 값(홀 지름 등)이 1% 안에 들어오는지 확인. 안 맞으면 스케일이 틀린 것
- 선 **굵기로 실체와 보조선을 가른다**. 부품 외곽은 굵고(예: lw 0.99) 치수 보조선은 얇다(0.43).
  이걸 안 나누면 치수선을 부품 외곽으로 착각한다

원이 폴리라인으로 근사돼 있을 수 있다(`get_drawings` 에 `c` 항목이 없다). 그때는 곡선이 아니라
**가로세로가 거의 같은 작은 닫힌 경로**를 원으로 본다. 스크립트가 둘 다 처리한다.

자세한 방법과 함정은 `references/drawing-measurement.md`.

## 5. 물리 형상을 설명 문자열로 추론하지 마라

**여기서 가장 크게 틀린다.** 데이터시트에 `right-angle` 이라고 적혀 있다고 바디 위치를
짐작하면 안 된다.

- 스트레이트형: 바디가 핀 격자 **위에** 있다
- 라이트앵글형: 접점이 하우징 뒤로 빠져 90도로 꺾여 내려온다 →
  **바디가 핀 격자를 아예 안 덮는다.** 격자 옆에 따로 있다

그리고 **바디가 직사각형이라고 가정하지 마라.** 마운팅 귀(ear)가 튀어나오고 그 안에 마운팅홀이
들어가는 형태가 흔하다. 도면에 전장(A)과 바디길이(B)가 따로 있으면 그 차이가 귀 돌출이다.

판정 순서:

1. 도면의 **평면도(plan view)** 를 찾는다. 핀 행과 하우징 외곽이 같이 나오는 뷰다
2. 하우징 외곽선(굵은 선)의 y 좌표를 **실측**해서 핀 행 대비 어디인지 본다
3. 치수 숫자의 **기준선이 어디인지** 확인한다. 예: `12.7` 이 하우징 깊이가 아니라
   "하우징 뒷면 → 첫 핀행" 거리일 수 있다. 실측값과 도면 숫자가 안 맞으면 기준선을 잘못 잡은 것
4. 비직사각형이면 외곽 폴리곤을 통째로 뽑아 `add_extruded_3d_body(outline_points_mils=...)` 로 넣는다

### 3D 모델

압출 바디 값은 데이터시트에서:

```python
fp.add_component_body_rectangle(
    left_mils=-D/2, bottom_mils=-E/2, right_mils=D/2, top_mils=E/2,
    overall_height_mils=A_NOM,      # 전고
    standoff_height_mils=A1_NOM,    # 안 주면 라이브러리 기본값(0.013mm)이 들어간다
)
```

- `standoff_height_mils` 를 **빼먹지 마라.** 생략하면 의도하지 않은 기본값이 들어간다
- 높이는 데이터시트 **A 의 MIN~MAX 안**에 있어야 한다. 기존 라이브러리 값이 규격 밖인
  경우가 있으니 **가져다 쓰기 전에 대조한다** (실제로 MIN 미만인 것을 발견한 적 있다)
- **3D 바디는 `altium-mcp` 전수 덤프에 안 나온다** (§6-2). `altium_monkey` 되읽기로 값을
  확인하고, 형상은 Altium 의 3D 뷰나 Models 패널에서 따로 본다
- 공용 3D 자산 폴더가 있으면 거기부터 본다 (`.../3D/<카테고리>/`).
  `IC.PcbLib` 바디 25개 중 19개 STEP 링크 / 6개 압출
- **STEP 은 PcbLib 안에 임베드된다. 공유 `3D\` 폴더에 넣을 필요 없다.**
  `.PcbLib` 하나만 있으면 3D 가 뜬다 (실측: zlib 66.7KB 로 저장, 되읽으면 360,010 바이트
  sha256 동일). 받은 STEP 원본은 `<작업폴더>/<부품>/3d/` 에 **빌드 입력**으로만 둔다 —
  재현용이지 배포물이 아니다

#### STEP 을 어디서 받나 — 무인증으로 되는 곳은 두 군데뿐이다

전부 **실제로 눌러서 확인한 것**이다 (2026-08-12).

| 소스 | 접근 | 포맷 | 판정 |
|---|---|---|---|
| **KiCad packages3D** (GitHub) | 무인증 200 | STEP | **1순위.** 범용·형상별 카탈로그 |
| 〃 GitLab 미러 | 무인증 200 | STEP | GitHub 죽었을 때 백업 |
| **EasyEDA / LCSC** | 무인증 200 | **STEP** + OBJ | 2순위. 부품별. 여분 형상 주의 |
| 벤더 KiCad repo (GitHub) | 무인증 200 | STEP | **그 회사 부품일 때만.** espressif 30개 / sparkfun 324개 / Digi-Key 0개 |
| easyw `kicad-3d-models-in-freecad` | 무인증 200 | cadquery 생성기 | 카탈로그에 없는 형상을 만들 때. FreeCAD/cadquery 필요 |
| SnapEDA | **403** | — | 계정 필요 |
| Component Search Engine | 웹 **403** / 모델 직다운 **401** / MCP 검색은 되나 `has_3d=false` | — | 계정 필요 |
| Ultra Librarian | **404** | — | 공개 API 없음 |
| Octopart · GrabCAD · 3Dfindit | **403** | — | 계정 필요 |
| TraceParts | 202 (JS 렌더) | — | 프로그램으로 못 받음 |
| 3D ContentCentral | **타임아웃** | — | 접근 불가 |

막힌 곳이 필요하면 **사람이 받아와야 한다.** 두 경로가 있다:

- Altium 의 **Manufacturer Part Search** 패널 — 계정으로 Altium 안에서 바로 모델을 가져온다.
  GUI 라 에이전트가 못 몬다
- CSE/SnapEDA 에 로그인해서 zip 을 받아오면 `lib_extract_cse_zip` 으로 설치 계획을 뽑을 수 있다
  (**`eda-agent` 도구다. 선택 사항** — 없으면 zip 을 직접 풀어 쓴다.
  `altium-mcp` 와 **동시에 띄우면 안 된다** → `references/tool-traps.md`)

**1순위 — KiCad packages3D.** 파일명이 형상 그 자체라 검색이 쉽다.

```
https://raw.githubusercontent.com/KiCad/kicad-packages3D/master/
    <라이브러리>.3dshapes/<형상명>.step
예: Package_DFN_QFN.3dshapes/QFN-32-1EP_4x4mm_P0.4mm_EP2.65x2.65mm.step
```

목록은 `https://kicad.github.io/packages3d/<라이브러리>.html` 또는 GitHub contents API
(`/repos/KiCad/kicad-packages3D/contents/<라이브러리>.3dshapes?per_page=100`).
QFN 폴더만 STEP 220개다. **EP 치수까지 파일명에 있으니 데이터시트 공차 안에 드는 걸 고른다**
(예: EP 규격 2.60/2.70/2.75 → `EP2.65x2.65` 채택, `EP2.9x2.9` 는 공차 밖이라 탈락).

라이선스: GPLv3 **+ 설계 사용 예외** — 설계에 임베드해도 그 설계가 GPL 이 되지 않는다.
파일 헤더에 예외 조항이 그대로 들어있다.

**2순위 — EasyEDA / LCSC.** 부품별이라 형상이 정확히 맞는다. 두 엔드포인트가 다르다:

```
modules.easyeda.com/3dmodel/<uuid>                      -> OBJ   (Altium 못 씀)
modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/<uuid>     -> STEP  (이걸 쓴다)
```

uuid 는 `lib_easyeda_import(lcsc_id=..., target='inspect')` 의 `model_3d_uuid`
(**`eda-agent` 도구, 선택 사항**). LCSC 부품번호는 `pcbparts` 의 `jlc_search` 로 찾는다
(EasyEDA 검색 API 는 죽어 있다). 둘 다 없으면 LCSC 사이트에서 부품번호를 직접 찾고
uuid 는 EasyEDA 부품 페이지에서 확인한다.

**[주의] EasyEDA 모델에는 여분 형상이 붙어 있을 수 있다.** 실제로 QFN 모델에서
바디·높이는 규격에 맞는데 **바닥 근처에 바디보다 훨씬 넓게 퍼진 평판**이 붙어 있는 것을 봤다.
그대로 쓰면 3D 에서 부품이 실제보다 크게 보여 기구 간섭 검토가 틀어진다.
**받으면 반드시 bbox 를 재라.**

#### 받은 STEP 은 붙이기 전에 실측한다

```python
# CARTESIAN_POINT 전수 스캔으로 bbox. CAD 커널 없이 된다.
pts = re.findall(r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(([-0-9.E+, ]+)\)", text)
```

- `LENGTH_UNIT` 을 먼저 확인한다. `SI_UNIT ( .MILLI., .METRE. )` 여야 mm 다
  (`SI_UNIT` 만 grep 하면 radian/steradian 만 잡히고 길이 단위를 놓친다)
- X·Y 폭 = 데이터시트 D·E, Z 높이 = A 범위 안인지 본다
- 바디(±D/2) **밖으로 나간 점의 비율과 그 Z 값**을 본다. 리드가 아니라 랜드 평판이면
  z 가 0~0.2 에 몰려 있다

#### 임베드

```python
model = pcblib.add_embedded_model(name=step.name, model_data=step.read_bytes())
fp.add_embedded_3d_model(model, bounds_mils=(-D/2, -E/2, D/2, E/2),
                         standoff_height_mils=0.0,   # 모델이 z=0 에서 시작하면 0
                         name=step.stem)
```

- 페이로드는 **zlib 압축되어 PcbLib 안에 들어간다.** 되읽어 `zlib.decompress` 하면
  원본과 sha256 이 같은지 확인할 수 있다 (실측: 360,010 바이트 그대로 복원)
- STEP 이 없으면 `add_component_body_rectangle` 로 폴백. **분기를 코드에 남겨라**
- **1번핀 방향 정렬은 좌표로 못 잡는다.** Altium 3D 뷰에서 눈으로 봐야 한다

## 6. 검증 — 개수는 검증이 아니다

`pads 98 / pins 96` 을 확인하고 넘어가면 안 된다. 그건 개수만 맞다는 뜻이다.
실제로 그 상태로 "검증 완료" 라고 했다가 파라미터 중첩·색 오류·z-order 가 전부 남아 있었다.

**3단계를 다 해야 한다:**

### 6-1. 라운드트립 (altium_monkey)

쓴 파일을 다시 읽어 좌표를 출력한다. **단위 오류가 여기서 잡힌다.**

`altium_monkey` 의 SchLib 은 **입력이 mil, 되읽으면 10mil 단위**다.
`AltiumSchPin(x=100, length=100)` → `location.x == 10`, `length_mils == 100.0`.
기준 심볼에서 읽은 값(`x=10`)을 그대로 넣으면 **10배 작아진다.**

### 6-2. Altium 전수 덤프 (altium-mcp)

내가 쓴 걸 내가 읽는 건 검증이 아니다. **Altium 이 같게 해석하는지** 봐야 한다.

```
get_footprint_primitives(library_path=..., footprint_name=...)   # 풋프린트 전수
get_symbol_primitives(library_path=..., symbol_name=...)         # 심볼 전수
```

원본을 열어두고 덮어쓰면 Altium 이 구버전을 물고 있으니, **사본을 다른 이름으로 만들어**
그걸 연다. 원본 문서는 건드리지 않는다.

이 덤프에 **안 나오는 것** 3가지를 기억할 것:
풋프린트 링크(implementation), 지정자, 3D 바디 형상. 이건 따로 확인해야 한다.

### 6-3. 눈으로 본다

**색·글자 중첩·z-order 는 좌표로 안 잡힌다.** 반드시 렌더한다.

- 풋프린트: `altium-mcp` 의 `get_screenshot(view_type='pcb')`
- 심볼: 스크린샷이 자주 실패한다(`references/tool-traps.md` 의 모달 버그).
  `AltiumSchLib.symbol_to_svg()` → pymupdf 로 PNG 변환해서 보는 게 안전하다

기준 심볼과 **나란히 렌더해서 비교**하면 색·배치 차이가 즉시 보인다.

### 판정 기준 — 이건 안 흔들린다

**최종 판정은 항상 Altium 이 읽은 값으로 한다.** `altium_monkey` 되읽기와 SVG 는
빠른 자체 점검일 뿐, 그것만으로 "검증했다" 고 하면 안 된다.

SVG 를 쓰는 건 스크린샷 버그를 피하려는 우회지 기준을 바꾸는 게 아니다.
**SVG 렌더러는 z-order 를 Altium 과 다르게 그린다** — SVG 에서 멀쩡해 보여도
Altium 에서는 본체가 핀 이름을 덮고 있을 수 있다. z-order 판정은 §2 의 레코드 순서로 한다.

| 확인할 것 | 무엇으로 |
|---|---|
| 좌표·개수·플래그 | `altium-mcp` 전수 덤프 (Altium 파싱) |
| 단위 오류 | `altium_monkey` 라운드트립 |
| 색·글자 중첩 | 렌더 (풋프린트=Altium 스크린샷 / 심볼=SVG) |
| z-order | `scripts/diff_symbol.py` 2층 (레코드 순서) |
| 풋프린트 링크·지정자·3D 형상 | 전수 덤프에 **안 나온다.** Altium 화면이나 Models 패널에서 따로 확인 |

## 7. 공유 라이브러리는 묻고 쓴다

여러 사람이 함께 쓰는 라이브러리에 **쓰기 전에는 반드시 확인받는다.**

- Altium 에서 그 파일이 **미저장 상태(`*`)** 면 디스크로 쓰면 충돌한다. 먼저 정리하게 한다
- 읽기는 자유. `altium_monkey` 로 헤드리스 조회하면 Altium 을 안 건드린다

작업 중 만든 검증용 사본(`*_chk.SchLib`, `*_v2.PcbLib` 등)은 **Altium 에서 열려 있을 수 있다.**
지우기 전에 저장 없이 닫으라고 안내한다.

## 관례

- **심볼 핀 배치는 패키지 순서가 기본이다.** 기능 그룹으로 바꾸려면 물어본다 (§3)
- **커넥터는 핀 번호(designator)를 숨긴다.** 번호와 이름이 같으면 두 번 찍혀 지저분하다.
  `AltiumSchPin(designator_visible=False)`
- **IC 는 핀 번호를 보여준다.** 패키지 순서 배치라도 번호가 있어야 대조가 된다
- 1번 핀은 **사각 패드**로 구분한다 (나머지 원형)
- 마운팅홀은 비도금(`plated=False`), 패드 지름 = 홀 지름
- 압출 3D 바디는 `standoff_height_mils` 를 반드시 명시한다 (§5)
- THT 패드 지름은 도면에 없는 경우가 많다. IPC-2222 Level B 통상값(홀 + 편측 0.35mm)을
  쓰되 **가정이라고 명시하고 사용자에게 확인받는다**
- 도면에 없어서 내가 정한 값은 **생성 코드 주석에 근거와 함께** 남긴다.
  나중에 "왜 이 값이지?" 를 푸는 유일한 기록이다

## 참고 파일

| 파일 | 언제 읽나 |
|---|---|
| `references/altium-monkey-api.md` | 코드를 쓰기 직전. 단위·시그니처·자주 쓰는 패턴 |
| `references/tool-traps.md` | altium-mcp/eda-agent 가 이상하게 굴 때 |
| `references/drawing-measurement.md` | 도면에서 치수를 떠야 할 때 |

| 스크립트 | 용도 |
|---|---|
| `scripts/survey_library.py` | 라이브러리에 뭐가 있는지 훑기 (§1) |
| `scripts/diff_symbol.py` | 기준 부품과 3층 비교 (§2) |
| `scripts/fit_symbol_body.py` | 심볼 본체 최소 크기 계산 (핀 이름 겹침 검사) (§3) |
| `scripts/measure_drawing.py` | PDF 도면 벡터 실측 (§4) |
