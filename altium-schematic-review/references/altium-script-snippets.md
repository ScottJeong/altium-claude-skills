# 검증된 DelphiScript 스니펫

`run_altium_script` 에 그대로 넣어 쓴다. **전부 실제로 통과한 것만** 적었다.
쓰기 전에 `altium-script-traps.md` 를 읽는다.

## 1. probe — 실행기가 살아있나

본 작업 전에 항상 먼저 돌린다. 실패하면 실행기가 멈춘 것이니 사용자에게 해제를 요청한다.

```pascal
SandboxLog('probe');
ResultText := 'alive';
Obj1 := GetWorkspace;
if Obj1 <> nil then
begin
    Obj2 := Obj1.DM_FocusedProject;
    if Obj2 <> nil then
        ResultText := 'alive | prj=' + Obj2.DM_ProjectFileName;
end;
SandboxLog('probe done');
```

기대 출력: `alive | prj=<이름>.PrjPcb`

## 2. 프로젝트 문서 목록

어떤 문서가 프로젝트에 속하는지 본다. **PcbDoc 존재 여부**는 `get_screenshot`
동작에도 영향을 주므로 알아둘 값이다.

```pascal
SandboxLog('start');
ResultText := '';
Obj1 := GetWorkspace;
Obj2 := Obj1.DM_FocusedProject;
if Obj2 = nil then
begin
    ResultText := 'NO FOCUSED PROJECT';
end
else
begin
    S1 := Obj2.DM_ProjectFileName;
    I1 := Obj2.DM_LogicalDocumentCount;
    ResultText := 'PRJ=' + S1 + ' | docs=' + IntToStr(I1);
    for I2 := 0 to I1 - 1 do
    begin
        Obj3 := Obj2.DM_LogicalDocuments(I2);
        ResultText := ResultText + ' | [' + IntToStr(I2) + '] ' +
                      Obj3.DM_DocumentKind + ' : ' + Obj3.DM_FullPath;
    end;
end;
SandboxLog('done');
```

`DM_DocumentKind` 값: `SCH`, `PCB`, `VirtualBOM` 등.

## 3. 컴파일 + 넷 개수 — 권위 대조의 핵심

**§2 권위 대조는 이것만으로 목적을 달성한다.** 내 파이썬 넷 개수와 비교해서
다르면 내 도구가 틀린 것이다.

```pascal
SandboxLog('start');
ResultText := '';
Obj1 := GetWorkspace;
Obj2 := Obj1.DM_FocusedProject;
SandboxLog('compile');
Obj2.DM_Compile;
SandboxLog('flattened doc');
Obj3 := Obj2.DM_DocumentFlattened;
if Obj3 = nil then
begin
    ResultText := 'FLATTENED = nil (컴파일 실패 가능)';
end
else
begin
    SandboxLog('net count');
    I1 := Obj3.DM_NetCount;
    I2 := Obj3.DM_ComponentCount;
    ResultText := 'nets=' + IntToStr(I1) + ' comps=' + IntToStr(I2);
    SandboxLog('sample nets');
    S1 := '';
    for I3 := 0 to I1 - 1 do
    begin
        if I3 > 7 then Break;
        Obj4 := Obj3.DM_Nets(I3);
        S1 := S1 + ' | ' + Obj4.DM_NetName + '(' + IntToStr(Obj4.DM_PinCount) + ')';
    end;
    ResultText := ResultText + S1;
end;
SandboxLog('done');
```

실측 출력 예:

```
nets=182 comps=164 | XSCO(3) | XSCI(4) | X2(2) | X1(3) | WO_MII_TXE(3) | ...
```

**주의**: `DM_Compile` 은 Messages 패널을 띄운다. 사용자에게 미리 알린다.

## 4. 넷 이름 + 핀 수 전량을 파일로

`ResultText` 는 길면 다루기 나쁘다. 파일로 떨구고 파이썬에서 읽는다.

```pascal
SandboxLog('start');
Obj1 := GetWorkspace;
Obj2 := Obj1.DM_FocusedProject;
SandboxLog('compile');
Obj2.DM_Compile;
Obj3 := Obj2.DM_DocumentFlattened;
if Obj3 = nil then
begin
    ResultText := 'FLATTENED nil';
end
else
begin
    SandboxLog('collect');
    List1.Clear;
    I1 := Obj3.DM_NetCount;
    for I2 := 0 to I1 - 1 do
    begin
        Obj4 := Obj3.DM_Nets(I2);
        List1.Add(Obj4.DM_NetName + '|' + IntToStr(Obj4.DM_PinCount));
    end;
    SandboxLog('save');
    List1.SaveToFile('C:\temp\nets.txt');   // 쓰기 가능한 임시 경로로 바꿔 쓴다
    ResultText := 'saved ' + IntToStr(List1.Count);
end;
SandboxLog('done');
```

## 5. 아직 못 한 것 — 핀 상세

넷별로 **핀까지** 순회하면 죽었다. `build list` 로그 직후 사망.

```pascal
// 이 형태가 죽었다. 그대로 쓰지 말 것.
Obj5 := Obj4.DM_Pins(I3);
List1.Add('  PIN|' + Obj5.DM_PhysicalPartDesignator + '|' +
          Obj5.DM_PinNumber + '|' + Obj5.DM_PinName + '|' +
          IntToStr(Obj5.DM_ElectricalType) + '|' +
          Obj5.DM_LogicalPartDesignator);
```

다음에 시도할 때는 **속성 하나씩** 붙여가며 확인한다:

```pascal
// 1단계: 핀 개수만
List1.Add(IntToStr(Obj4.DM_PinCount));
// 2단계: 지정자만
Obj5 := Obj4.DM_Pins(0);
List1.Add(Obj5.DM_PhysicalPartDesignator);
// 3단계: 핀번호 추가 … 이런 식으로
```

**핀 상세가 필요하면 파이썬 `net_erc.py` 로 대체 가능하다.** 그쪽은 Altium 과
넷 개수가 일치하는 것까지 확인됐다. Altium 스크립트는 **개수 대조용**으로만 써도
목적을 달성한다.
