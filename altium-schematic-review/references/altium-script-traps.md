# `run_altium_script` 함정 — 쓰기 전에 읽는다

이 도구는 Altium 자체 API 를 부를 수 있어서 강력하다. 대신 **잘못 쓰면 Altium 을 마비시킨다.**

## 가장 중요한 것 — 실행기가 멈춘다

DelphiScript 에서 런타임 에러가 나면 **스크립트가 디버거에 멈춘 채 남는다.**
그 뒤로는:

```
{"success": false, "error": "script never started",
 "executor_wedged": true}
```

**이후 모든 `run_altium_script` 호출이 조용히 실패한다.**

### 범위 — altium-mcp 도구 전부가 막힌다

도구 설명에는 이렇게 적혀 있다:

> *"The script runs in a SEPARATE script project, so a crash here can never break
> the other MCP tools."*

**이 문장은 틀렸다.** 실측으로 반증됐다. 다른 도구를 부르면 Altium 이 이 다이얼로그를 띄운다:

```
Another script executing now.
Scripting system is not able to execute more than one script simultaneously.
```

**Altium 의 스크립팅 실행 슬롯은 전역으로 하나다.** 스크립트 프로젝트가 분리돼 있어도
동시에 두 개를 못 돌린다. 따라서 sandbox 가 멈추면
`get_footprint_primitives`·`get_symbol_primitives`·`search_library_symbol`·
`get_screenshot` 까지 **전부** 막힌다.

살아있는 것은 `get_server_status` 정도다 — 그건 프로세스·파일 존재만 확인하고
스크립트를 안 돌린다.

**그래서 이 도구는 "실패해도 다른 게 살아있겠지" 라고 생각하고 쓰면 안 된다.**
한 번 잘못 쓰면 Altium 연동 전체가 정지한다.

### 증상

- Altium 메인 창 제목이 **`Sandbox.PrjScr`** 로 바뀐다
- 스크립트 편집기에 `sandbox.pas` 가 열려 있고 어느 줄에 멈춰 있다
- 호출마다 `dialogs_dismissed: 1` 이 붙는다

### 해제 (사용자가 해야 한다)

1. Altium 에서 **`sandbox.pas` 편집기 코드 영역을 클릭**해 포커스를 준다
2. **`Ctrl+F3`** (메뉴 `Run → Stop`)
3. 안 되면 `Run → Reset Script`, 그래도 안 되면 Altium 재시작

`Ctrl+F3` 는 **편집기에 포커스가 있어야** 먹는다. 회로도나 Messages 창에 포커스가
있으면 다른 동작이 걸린다.

**에이전트가 스스로 풀 수 없다.** 멈췄으면 즉시 사용자에게 알리고 기다린다.
멈춘 채로 계속 호출해봐야 시간만 버린다.

## 그래서 이렇게 쓴다

### 작게 나눈다

한 번에 하나씩. "컴파일 + 넷 개수" 까지는 안전했고, 거기에 "핀 전부 순회" 를
얹은 순간 죽었다.

### `SandboxLog` 를 문장마다 넣는다

실패하면 **마지막으로 찍힌 로그 다음 문장**이 범인이다. 이게 유일한 단서다.

```pascal
SandboxLog('compile');
Obj2.DM_Compile;
SandboxLog('flattened');
Obj3 := Obj2.DM_DocumentFlattened;
```

루프 안에서 죽을 것 같으면 **루프 안에도** 로그를 넣는다 (인덱스 포함).

### 먼저 살아있는지 확인한다

본 작업 전에 최소 스크립트로 확인한다. `altium-script-snippets.md` 의 `probe`.

### `try/except` 를 믿지 마라

도구 설명 원문: *"try/except does NOT catch runtime errors such as bad conversions
or invalid API calls"*. 방어 코드로 못 막는다. **애초에 안 죽을 코드를 쓴다.**

### 변수는 주어진 것만

인라인 변수 선언이 없다. 제공되는 것만 재사용한다:

```
S1..S3   (String)
I1..I3, B1  (Integer)
Obj1..Obj5  (IDispatch)
List1  (TStringList)
IntMan, DbDoc
```

`Obj1~Obj5` 뿐이라 중첩 순회에서 객체가 모자라기 쉽다. **파일로 덤프하고
파싱은 파이썬에서** 하는 편이 안전하다.

## 죽은 사례 — 넷별 핀 순회

```pascal
Obj5 := Obj4.DM_Pins(I3);
List1.Add('PIN|' + Obj5.DM_PhysicalPartDesignator + '|' +
          Obj5.DM_PinNumber + '|' + Obj5.DM_PinName + '|' + ...);
```

`build list` 로그 직후 죽었다. 의심 순서:

1. 존재하지 않는 속성 (`DM_PinName` 등 — 인터페이스마다 이름이 다르다)
2. 빈 값 반환 후 문자열 결합 실패
3. 핀이 0개인 넷

**대책**: 속성을 하나씩만 붙여가며 시험한다. 한 번에 다섯 개를 결합하면
어느 것이 문제인지 알 수 없다.

## 안전한 것으로 확인된 호출

아래는 실제로 통과했다.

```pascal
GetWorkspace
  .DM_FocusedProject
    .DM_ProjectFileName
    .DM_LogicalDocumentCount
    .DM_LogicalDocuments(i).DM_DocumentKind / .DM_FullPath
    .DM_Compile
    .DM_DocumentFlattened
      .DM_NetCount / .DM_ComponentCount
      .DM_Nets(i).DM_NetName / .DM_PinCount
```

## 부수 효과를 예상하고 알린다

`DM_Compile` 은 **Messages 패널을 띄운다.** 사용자 화면에 창이 뜨므로 미리 말해둔다.
컴파일 자체는 문서를 바꾸지 않지만, 사용자가 놀라지 않게 하는 게 낫다.
