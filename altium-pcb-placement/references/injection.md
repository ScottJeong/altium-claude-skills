# 좌표 투입 (D)

**사용자가 "이대로 확정" 이라고 말하기 전에는 이 단계를 시작하지 않는다.**
가안이 2~4회 바뀌는 건 정상이고, 매번 PcbDoc 을 건드리면 되돌릴 게 쌓인다.

## 전제

1. **Update PCB from Schematic 이 먼저다.** PcbDoc 이 비어 있으면 넣을 컴포넌트가 없다.
   `AltiumPcbDoc.from_file(...)` 로 `len(p.components)` 를 확인한다. 0 이면 아직이다
2. Altium 이 그 PcbDoc 을 열고 있어야 한다 (`place_components` 는 라이브 세션 조작)
3. 지정자 대조 — `get_all_designators` 결과와 가안의 지정자가 맞는지 본다.
   가안에 `D1/D2` 같은 묶음 표기가 있으면 실패한다. 미리 나눈다

## 어느 도구로 넣나

**`altium-mcp` `place_components`** 를 쓴다.

- 절대 좌표 배치 전용 API. 여러 개를 한 트랜잭션으로 넣어 **undo 1단계**
- 반환값에 Altium 이 보고하는 **최종 x/y/rotation/layer** 가 들어 있다 → 대조에 쓴다
- `set_component_position` 은 1개씩이라 왕복이 많다. `move_components` 는 **상대 이동**이라
  절대 배치에 쓰면 안 된다

`altium_monkey` 로 PcbDoc 을 직접 고치는 길도 있으나, 그 파일은 지금 Altium 이 쥐고 있다.
**열려 있는 문서를 파일로 덮어쓰면 충돌한다.** 생성은 monkey, 라이브 조작은 mcp 다.

## 단위·기준이 다르다 — 그대로 넣으면 어긋난다

| 가안 | Altium |
|---|---|
| mm | **mils** (1mm = 39.3700787) |
| bbox 좌하단 + 폭/높이 | **컴포넌트 원점** |
| — | rotation = **반시계(CCW) 도** |

**컴포넌트 원점은 bbox 중심이 아니다.** 풋프린트를 그린 사람이 정한 자리라
pad1 일 수도, 몸체 중심일 수도, 엉뚱한 곳일 수도 있다. 부품마다 다르다.

## 2패스

```
1패스  bbox 중심을 원점이라 가정하고 place_components
2패스  실제 bbox 중심을 읽어 (의도한 중심 − 실제 중심) 만큼 보정해 다시 place_components
```

```
python scripts/plan_to_placements.py plan.json > p1.json
   → place_components(placements=<p1.json 내용>)
   → 실제 bbox 읽기
   → offsets.json 작성  {"U2": [dx_mil, dy_mil], ...}
python scripts/plan_to_placements.py plan.json --offsets offsets.json > p2.json
   → place_components(placements=<p2.json 내용>)
```

실제 bbox 를 읽는 방법(둘 중 되는 것):

- `altium-mcp` `get_component_data` / `get_selected_components_coordinates`
- 저장 후 헤드리스 — `AltiumPcbDoc.get_component_primitives(des)` 로 프리미티브
  bbox 를 내고, `get_component_origin_mils(des)` 와의 차를 구한다

**1패스 결과를 안 읽으면 2패스를 못 한다.** 넣고 끝내면 어긋난 걸 모른다.

## 보드 외곽·원점

- 가안 좌표는 **보드 좌하단 원점**이다. Altium 의 원점이 다르면
  `plan_to_placements.py --origin X_MM Y_MM` 로 오프셋을 준다
- 보드 외곽은 배치보다 **먼저** 잡는다. 외곽이 없으면 어긋난 걸 눈으로 못 본다

### 외곽·고정홀은 파일로 넣는다

`altium-mcp` 에는 외곽 API 가 없다. `eda-agent` 는 자체 폴링 루프를 Altium 안에
띄워야 하고 **스크립팅 슬롯이 전역 1개**라 그걸 띄우면 altium-mcp 브릿지가 죽는다.
`run_altium_script` 로 그리는 것도 `TPolySegment` 레코드를 담을 변수가 없어 불가능하다.

남는 길은 `altium_monkey` 로 파일을 직접 쓰는 것뿐이다 → `scripts/apply_outline.py`.

**Altium 이 그 문서를 열고 있으면 안 된다.** 순서:

```
0. 백업                             (스크립트가 <파일>.bak 을 자동으로 뜬다)
1. 사용자가 Altium 에서 Ctrl+S      (메모리 배치를 디스크로)
2. apply_outline.py 로 제자리 수정   (백업 먼저 뜬다)
3. Altium 이 "파일 바뀜, reload?" → Yes
```

1번을 건너뛰면 Altium 이 저장할 때 외곽이 덮인다. 디스크 mtime 과 부품 좌표를
읽어 저장됐는지 **확인한 뒤** 쓴다.

### 함정 — 오서링 빌더가 직접 수정을 삼킨다

`set_board_outline()` / `set_outline_*()` 을 부르면 오서링 빌더가 상태를
스냅샷한다. **같은 세션에서 프리미티브 객체를 직접 고친 것은 저장에서 사라진다.**
호출 순서를 바꿔도(패드 먼저, 외곽 나중) 소용없다.

그래서 **2패스**로 나눈다.

```python
# 패스1 — 패드 직접 수정
p.x = ...; p.y = ...
p._raw_binary = None      # 패드는 원본 바이너리를 캐시한다. 안 지우면 좌표가 안 바뀐다
d.save(path)

# 패스2 — 다시 읽고 외곽
d = AltiumPcbDoc.from_file(path)
d.set_board_outline(...)
d.save(path)
```

`_raw_binary = None` 을 빼먹으면 메모리 값은 바뀌었는데 저장은 옛 좌표다.
**저장 후 다시 읽어 검산하지 않으면 이걸 못 잡는다.**

## 회전

- `plan.json` 의 `rot` 은 그대로 CCW 도로 나간다. `pin_side_map.py` 출력과 같은 규약
- 회전을 바꾸면 bbox 가 바뀌므로 **2패스 보정값도 달라진다.** 회전을 먼저 확정하고 넣는다

## 스크립팅 도구를 함부로 쓰지 않는다

`run_altium_script` 로 배치를 하려 들지 마라. 런타임 에러가 나면 스크립트가 디버거에
멈추고 **Altium 의 스크립팅 슬롯은 전역으로 하나뿐**이라 그때부터 다른 altium-mcp 도구까지
전부 막힌다 (`Another script executing now.`). **사람이 `Ctrl+F3` 를 눌러야 풀린다.**
`place_components` 로 되는 일에 스크립트를 쓸 이유가 없다.

## 투입 후

- **다시 스크린샷을 찍어 가안과 대조한다.** 숫자가 맞아도 그림이 다를 수 있다
- 어긋난 게 있으면 가안 JSON 이 아니라 **offsets 를 고친다.** 가안은 의도의 기록이다
