# altium_monkey API — 단위·시그니처·함정

코드를 쓰기 직전에 읽는다. 아래는 실제로 돌려보고 확인한 것만 적었다.

## 목차

- [인터프리터](#인터프리터)
- [단위 — 가장 많이 틀리는 곳](#단위--가장-많이-틀리는-곳)
- [PcbLib](#pcblib)
- [SchLib](#schlib)
- [읽기(라운드트립) API](#읽기라운드트립-api)
- [원시 레코드](#원시-레코드)
- [색](#색)

## 인터프리터

```
python
```

3.12 venv. `altium-monkey` 는 `Requires-Python <3.13,>=3.12` 라 시스템 3.13 에서는
"패키지가 없다" 는 오해를 부르는 오류로 실패한다. 실제로는 인터프리터가 너무 새것이다.

venv 에 `pip` 가 없다. 패키지 추가는:

```
uv pip install --python python pymupdf
```

## 단위 — 가장 많이 틀리는 곳

| 영역 | 입력 | 되읽기 |
|---|---|---|
| PCB (`add_pad`, `add_track` …) | **mil** | **mil** (`x_mils`, `start_x_mils` …) |
| SCH (`AltiumSchPin`, `add_rectangle` …) | **mil** | **10mil 단위** (`location.x`, `length`) |

SCH 쪽이 비대칭이라 사고가 난다:

```python
AltiumSchPin(x=100, length=100)   # 입력은 mil
# 되읽으면
p.location.x   # -> 10      (10mil 단위)
p.length       # -> 10      (10mil 단위)
p.length_mils  # -> 100.0   (mil)
```

**기준 심볼에서 읽은 값을 그대로 입력에 넣으면 10배 작아진다.**
되읽은 값은 `*_mils` 접근자를 쓰거나 10을 곱해서 비교할 것.

mm 로 작업하려면 상수 하나 두고 곱한다:

```python
MM = 1000.0 / 25.4      # mm -> mil
PITCH = 2.54 * MM       # 100.0 mil  (2.54mm 격자는 정수 mil 로 떨어져서 편하다)
```

## PcbLib

```python
from altium_monkey import AltiumPcbLib
from altium_monkey.altium_pcb_enums import PadShape
from altium_monkey.altium_record_types import PcbLayer

lib = AltiumPcbLib()
fp = lib.add_footprint("NAME", height="11mm", description="...")

fp.add_pad(
    designator="A1",
    position_mils=(x, y),
    width_mils=d, height_mils=d,
    layer=PcbLayer.MULTI_LAYER,
    shape=PadShape.RECTANGLE,      # 1번핀만 사각, 나머지 CIRCLE
    hole_size_mils=hole,
    plated=True,                    # 마운팅홀은 False
)

fp.add_track((x1, y1), (x2, y2), width_mils=8, layer=PcbLayer.TOP_OVERLAY)

# 비직사각형 3D 바디 — 폴리곤 그대로 압출
fp.add_extruded_3d_body(
    outline_points_mils=[(x, y), ...],
    overall_height_mils=h,
    standoff_height_mils=0.0,
    name="housing",
)

# 직사각형이면 이쪽이 짧다
fp.add_component_body_rectangle(
    left_mils=..., bottom_mils=..., right_mils=..., top_mils=...,
    overall_height_mils=h,
)

lib.save(path)
```

`PcbLayer` 주요 멤버: `TOP`, `BOTTOM`, `MULTI_LAYER`, `TOP_OVERLAY`, `BOTTOM_OVERLAY`,
`KEEPOUT`, `MECHANICAL_1` ~ `MECHANICAL_16`, `TOP_PASTE`, `TOP_SOLDER`, `DRILL_DRAWING`.

`PadShape`: `CIRCLE=1`, `RECTANGLE=2`, `OCTAGONAL`, `ROUNDED_RECTANGLE`.

관례상 `MECHANICAL_1` = 보드 엣지/조립 표시, `MECHANICAL_15` = 코트야드로 쓴다
(프로젝트마다 다르니 기존 풋프린트를 보고 맞출 것).

## SchLib

```python
from altium_monkey import (AltiumSchLib, AltiumSchPin, LineWidth,
                           PinElectrical, PinOrientation)

lib = AltiumSchLib()                    # 새로 만들 때
lib = AltiumSchLib(path)                # 기존 파일 열 때 (from_file 아님!)

sym = lib.add_symbol("NAME", description="...")
sym.set_part_count(3)                   # 멀티파트

# 사각형을 핀보다 **먼저** 넣는다 — z-order. 아래 [함정] 참조
sym.add_rectangle(x1, y1, x2, y2,
                  color=0x000080, area_color=0xB0FFFF,
                  line_width=LineWidth.SMALLEST,
                  owner_part_id=part)

pin = AltiumSchPin(
    designator="A1", name="A1",
    x=100, y=0,                          # mil
    orientation=PinOrientation.LEFT,     # RIGHT=0 UP=1 LEFT=2 DOWN=3
    length=100,                          # mil
    electrical_type=PinElectrical.PASSIVE,
    owner_part_id=part,                  # 1-based
    designator_visible=False,            # 커넥터는 보통 끔
    name_visible=True,
)
sym.add_pin(pin)

sym.add_designator("J?", x=-50, y=50)
sym.add_parameter("Comment", "...", x=-50, y=-150)
sym.add_parameter("Manufacturer", "...", x=-50, y=-150, is_hidden=True)
sym.add_footprint("FOOTPRINT-NAME", library_name="LIBNAME")

lib.save(path)
```

`PinElectrical`: `INPUT=0 IO=1 OUTPUT=2 OPEN_COLLECTOR=3 PASSIVE=4 HIZ=5 OPEN_EMITTER=6 POWER=7`.
커넥터·헤더는 `PASSIVE`.

`LineWidth`: `SMALLEST=0 SMALL=1 MEDIUM=2 LARGE=3`.

### [함정] z-order — 사각형을 핀보다 먼저

Altium 은 **레코드 순서대로 그린다.** 채워진(`is_solid=True`) 사각형을 핀 **뒤에** 넣으면
본체가 핀 이름 글자를 덮어서 안 보인다. 좌표는 다 맞는데 화면만 이상해지므로
좌표 검산으로는 절대 안 잡힌다.

파트별로 `add_rectangle` → 그 파트 핀들 순서로 넣는다. 확인은 레코드 순서로:

```
정상: 1x1  14x1  2x32  14x1  2x32  14x1  2x32  34x1 ...
불량: 1x1  2x32  14x1  2x32  14x1  2x32  14x1  34x1 ...
      (RECORD 14=사각형, 2=핀)
```

### [함정] 파라미터를 좌표 없이 넣으면 원점에 쌓인다

`add_parameter(name, text)` 만 쓰면 전부 `(0,0)` 에 겹쳐서 심볼 위에 글자가 뭉갠다.
보이게 할 것 하나만 좌표를 주고 나머지는 `is_hidden=True`.

## 읽기(라운드트립) API

```python
# PcbLib
back = AltiumPcbLib.from_file(path)
for f in back.footprints:
    for p in f.pads:
        p.designator, p.x_mils, p.y_mils
    for t in f.tracks:
        t.start_x_mils, t.start_y_mils, t.end_x_mils, t.end_y_mils, t.width_mils, t.layer
    f.component_bodies

# SchLib
names = AltiumSchLib.get_symbol_names(path)   # 정적 — 인스턴스 아님, 경로를 받는다
lib = AltiumSchLib(path)
sym = lib.get_symbol(name)
sym.part_count, sym.pins, sym.rectangles, sym.designators, sym.parameters, sym.implementations
p.location.x, p.location.y      # CoordPoint, 10mil 단위
p.length_mils, p.orientation_name, p.electrical_name, p.owner_part_id
r.location.x, r.corner.x, r.color, r.area_color, r.line_width, r.is_solid
```

주의: `AltiumSchLib` 에는 `from_file` 이 **없다**. 생성자에 경로를 넘긴다.
`AltiumPcbLib` 에는 `from_file` 이 **있다**. 비대칭이다.

## 원시 레코드

`sym.raw_records` — dict 리스트. 핀은 바이너리다.

| RECORD | 뜻 |
|---|---|
| 1 | 컴포넌트 |
| 2 | 핀 (바이너리, `__BINARY_DATA__`) |
| 14 | 사각형 |
| 34 | 지정자 |
| 41 | 파라미터 |
| 44 / 45 / 46 / 48 | 풋프린트 링크(implementation) 관련 |

핀 바이너리 **offset 15 = 플래그 바이트**. 실측으로 확인된 비트:

| 비트 | 뜻 |
|---|---|
| `0x08` | 핀 이름 표시 |
| `0x10` | 핀 번호(designator) 표시 |
| `0x20` | altium_monkey 가 `is_not_accessible` 로 노출하는 것 |

`0x20` 의 실제 의미는 확인 안 됐다. 사내 심볼은 전 핀에 켜져 있다.
기준 심볼과 바이트를 맞추려면 `pin.is_not_accessible = True` 로 생성 후 설정한다.

## 색

Altium 색 정수는 **BGR** 이다.

| 값 | RGB | 용도 |
|---|---|---|
| `0x000080` | (128, 0, 0) 적갈색 | 심볼 본체 테두리 |
| `0xB0FFFF` | (255, 255, 176) 연노랑 | 심볼 본체 채움 |
| `0x800000` | (0, 0, 128) | 지정자 텍스트 (사내 값) |

`add_rectangle` 기본값은 검정 테두리 + 흰 채움이라 **사내 심볼과 눈에 띄게 다르다.**
반드시 기준 심볼에서 읽어 맞출 것.
