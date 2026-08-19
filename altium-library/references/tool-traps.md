# EDA 도구 함정

`altium-mcp` / `eda-agent` 가 이상하게 굴 때 읽는다. 전부 실측으로 확인한 것이다.

## 목차

- [altium-mcp 스크린샷이 모달을 띄운다](#altium-mcp-스크린샷이-모달을-띄운다)
- [altium-mcp 는 상주 브릿지가 필요 없다](#altium-mcp-는-상주-브릿지가-필요-없다)
- [열린 라이브러리는 다시 안 읽는다](#열린-라이브러리는-다시-안-읽는다)
- [altium-mcp 로 생성하지 않는 이유](#altium-mcp-로-생성하지-않는-이유)
- [eda-agent](#eda-agent)

## altium-mcp 스크린샷이 모달을 띄운다

증상: `get_screenshot(view_type='sch')` 를 불렀는데 Altium 에

```
Error: No PCB document found in the project.
```

모달이 뜬다. **모달이 뜨면 스크립트 브릿지가 막혀서 이후 MCP 호출이 전부 타임아웃난다.**

원인 — `AltiumScript/other_utils.pas`:

```pascal
// 158~160행: view_type 과 무관하게 하드코딩
(CommandName = 'take_view_screenshot')  then
begin
    DocumentKind := 'PCB';
end
```

`view_type` 인자는 **문서 포커스 단계에서 무시된다.** 무조건 PCB 문서를 찾는다.
포커스된 프로젝트의 `DM_LogicalDocuments` 에 PcbDoc 이 없으면 325~327행에서 `ShowMessage`.

**간헐적인 이유**: 215~221행에서 `PCBServer.GetCurrentPCBBoard` 가 nil 이 아니면 조기 통과한다.
직전에 PcbDoc/PcbLib 을 본 적 있으면 그 보드가 살아 있어 그냥 넘어간다.

또한 free document(프로젝트에 안 속한 파일)는 `DM_LogicalDocuments` 에 안 들어간다.
독립 SchLib 을 열어두고 스크린샷을 찍으면 거의 확실히 실패한다.

**대응**

- 심볼은 스크린샷 대신 `symbol_to_svg()` → PNG 로 본다 (Altium 을 안 건드린다)
- 굳이 Altium 화면이 필요하면 같은 프로젝트에 PcbDoc 을 하나 열어둔다
- 모달이 떴으면 사용자에게 닫아달라고 하고, 닫힐 때까지 MCP 호출을 멈춘다

**이 경로를 안 타는 안전한 도구** (`other_utils.pas` 129~132행 스킵 목록):
`search_library_symbol`, `get_symbol_primitives`, `get_footprint_primitives`,
`create_symbols_batch`. 이것들은 문서 관리를 스스로 해서 모달을 안 띄운다.

## altium-mcp 는 상주 브릿지가 필요 없다

`eda-agent` 와 다르다. `eda-agent` 는 Altium 에서 `StartMCPServer` 를 매 세션 돌려야 하고
10분 무응답이면 죽는다. `altium-mcp` 는 **MCP 서버가 호출마다 스크립트를 Altium 에 던진다.**

`get_server_status` 가 `"server": "Running"` 이면 바로 쓸 수 있다.

## 열린 라이브러리는 다시 안 읽는다

`get_footprint_primitives(library_path=...)` 문서 원문:
*"an already-open library is only focused, never reloaded"*.

즉 **파일을 재생성해도 Altium 이 열어둔 문서는 구버전 그대로다.**
검증하려면 **다른 이름으로 사본을 만들어** 그걸 연다:

```
Copy-Item <이름>.PcbLib <이름>_chk.PcbLib -Force
get_footprint_primitives(library_path=".../<이름>_chk.PcbLib", footprint_name="...")
```

사용자가 열어둔 원본은 건드리지 않는 편이 안전하다. 원본에 미저장 변경(`*`)이 있으면
사용자가 저장하는 순간 내가 쓴 내용이 날아간다.

## altium-mcp 로 생성하지 않는 이유

`create_schematic_symbol` / `create_pcb_footprint` 는 **실행 중 Altium 의 활성 문서에 쓴다.**

- 어느 문서가 활성인지 확실히 보장하기 어렵다 → 남의 라이브러리를 오염시킬 수 있다
- 결과가 메모리에만 남는다. 저장 전에는 디스크에 없어서 헤드리스 검증이 불가능하다
- `create_pcb_footprint` 의 패드 포맷에 **홀 지름 파라미터가 없다** —
  `"pad|x|y|w|h|shape"` 뿐이라 THT 를 제대로 못 만든다

`create_schematic_symbol` 참고 사실 (직접 만들 일이 있을 때만):

- 핀 포맷 `"번호|이름|타입|방향|x|y[|owner_part_id[|length[|show_name[|show_designator]]]]"`
- 방향 `eRotate0`(오른쪽) `eRotate90`(아래) `eRotate180`(왼쪽) `eRotate270`(위)
- 좌표는 mil
- **본체 사각형은 핀 x 값의 min~max 로 자동 생성**된다 (`schematic_utils.pas` 317~324행).
  `graphics` 를 주면 자동 생성이 꺼진다
- **데이터시트 PDF 를 먹지 않는다.** 구조화된 핀 리스트를 요구한다 — 해석은 호출자 몫

## altium_monkey 가 못 읽는 풋프린트가 있다

일부 `.PcbLib` 풋프린트에서 파싱이 깨진다:

```
SubRecord 5 shorter than expected: 106 bytes (expected >=110)
```

경고를 stdout 으로 수백 줄 쏟아내고, 그 풋프린트의 `pads` 접근이 `AttributeError` 가 된다.
`scripts/survey_library.py` 는 이 경고를 삼키고 `<파싱실패 …>` 로만 표시한다.

읽을 수 없는 풋프린트는 **`altium-mcp` 의 `get_footprint_primitives` 로 읽으면 된다.**
Altium 이 직접 파싱하므로 이 문제가 없다. 기준 부품이 하필 이 케이스면 그쪽을 쓴다.

## Altium 이 저장할 때 채우는 값이 있다

altium_monkey 로 만든 풋프린트를 Altium 이 열고 저장하면, 원본에 없던 값이 채워진다:

```
soldermask_expansion_mils            생성본 0.0   →  Altium 저장 후 4.0
cache_power_plane_clearance          0            →  200000
cache_relief_air_gap                 0            →  100000
```

캐시성 값이라 대개 문제가 없지만, **솔더마스크 확장은 실물에 영향이 있다.**
생성본을 그대로 거버로 뽑기 전에 패드의 solder mask expansion 이 의도대로인지
(룰 기반인지 수동 0 인지) 한 번 확인할 것.

## eda-agent

- **한글이 `?` 로 깨진다.** DelphiScript 가 단일바이트라 Latin-1 초과 문자가 전부 물음표가 된다.
  읽기만 하면 표시 문제지만 **읽고 되쓰면 파일에 `?` 가 박힌다.**
  한글이 든 문서에 쓰기를 돌리기 전에 더미로 왕복 확인할 것
- read-only 모드가 없다. `EDA_AGENT_TOOLSET` 은 툴 **광고**만 제어하고 전부 호출 가능하다
- Altium 쪽 등록이 필요하다:
  `DXP → Preferences → Scripting System → Global Projects → Install from file`
  후 `File → Run Script... → Altium_API → Dispatcher.pas → StartMCPServer`.
  **세션마다** 다시 해야 한다
- `eda-agent` 와 `altium-mcp` 는 **Altium 스크립트 이름이 같다** (`Altium_API.PrjScr`).
  둘을 동시에 Global Projects 에 넣으면 어느 쪽이 뜨는지 알 수 없다. 하나씩 등록한다
- ECO 는 스크립트로 안 된다. `proj_sync_pcb` 가 조용히 아무것도 안 할 수 있다.
  결과 건수가 0이면 Altium 에서 `Design → Import Changes` 를 직접 눌러야 한다
