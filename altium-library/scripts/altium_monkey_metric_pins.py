"""SchLib 핀 좌표·길이의 10mil 미만 정밀도(메트릭 격자)를 살리는 altium_monkey 패치.

Altium 은 SchLib 핀의 위치·길이를 핀 레코드에 **10mil 단위 정수**로 쓰고, 나머지를
심볼별 `PinFrac` 스트림에 1/10000 mil 단위로 따로 둔다 (int32 3개: x_frac, y_frac,
length_frac). 각 항목의 키는 심볼 안 **핀 순번을 ASCII 문자열**로 쓴 것이다 ("0" … "12").

altium_monkey 2026.9.22 는 세 군데서 이걸 잃어서 핀이 10mil 격자로 깎인다:

  1. AltiumSchPin(x=..., y=..., length=...) 가 `x // 10` 으로 나머지를 버린다
     (음수는 Altium 처럼 0 쪽 절삭이 아니라 내림이 된다)
  2. PinFrac 을 쓸 때 키를 ASCII 순번이 아니라 원시 바이트(chr(index))로 쓴다
     → Altium 이 항목을 핀에 못 붙이고 무시한다
  3. SchLib 을 읽을 때 PinFrac 을 핀에 적용하지 않는다 → 원본 Altium 파일도 깎여 읽힌다

메트릭 격자 심볼(예: 5mm = 196.8504mil 핀)을 복사하면 197 → 190, 1063 → 1060 이 된다.
좌표가 다 10mil 배수인 심볼은 영향이 없다.

사용 — altium_monkey 로 SchLib 을 읽거나 쓰기 **전에** import 한다:

    import altium_monkey_metric_pins  # noqa: F401  (import 만으로 패치된다)
    from altium_monkey import AltiumSchLib, AltiumSchPin
    MM = 1000.0 / 25.4
    pin = AltiumSchPin(designator="1", name="IN", x=5 * MM, y=27 * MM, length=5 * MM, ...)

CLI — 심볼별 핀의 정확한 좌표·길이(mil, mm)를 찍는다. 메트릭 심볼 확인용:

    python altium_monkey_metric_pins.py <파일.SchLib> [--symbol 이름]

venv 전체에 항상 걸고 싶으면 venv 의 site-packages 에 이 파일과 함께
`altium_monkey_metric_pins.pth` (내용: `import altium_monkey_metric_pins`) 를 둔다.

검증 (2026-10-10, altium_monkey 2026.9.22, Altium Designer 25):
  - Altium 이 쓴 메트릭 심볼(13핀, 5mm 핀)을 읽어 그대로 새 SchLib 로 쓰고 Altium 에서
    Pin.Location.X/Y · Pin.PinLength 를 원본과 비교 → 내부 단위(1/10000 mil)까지 전부 동일
  - 음수 메트릭 좌표(-15mm, -10mm)도 Altium 에서 정확히 읽힘
  - get_symbol_primitives 는 mil 정수로 반올림해 보여주므로 이 비교에는 못 쓴다

다른 altium_monkey 버전에서는 내부 함수가 바뀌었을 수 있다. 확인된 버전이 아니면
경고만 내고 패치는 그대로 건다 — 위 방식으로 Altium 에서 한 번 대조할 것.
"""

from __future__ import annotations

import argparse
import struct
import sys
import warnings
from importlib.metadata import PackageNotFoundError, version

import altium_monkey.altium_record_sch__pin as _pin_mod
import altium_monkey.altium_schlib as _schlib_mod
import altium_monkey.altium_schlib_aux_streams as _aux_mod
from altium_monkey.altium_sch_auxiliary_codec import (
    SchAuxiliaryStreamError,
    decode_auxiliary_stream,
    encode_auxiliary_stream,
)

VERIFIED_VERSIONS = {"2026.9.22"}
UNITS_PER_MIL = 10_000
UNITS_PER_WHOLE = 100_000  # 10mil 한 칸

try:
    _AM_VERSION = version("altium-monkey")
except PackageNotFoundError:
    _AM_VERSION = "unknown"
if _AM_VERSION not in VERIFIED_VERSIONS:
    warnings.warn(
        f"altium_monkey_metric_pins: verified on {sorted(VERIFIED_VERSIONS)}, "
        f"running {_AM_VERSION}. Re-check pin coordinates in Altium.",
        stacklevel=2,
    )


def split_mils(value_mils: float) -> tuple[int, int]:
    """mil 값을 (10mil 단위 정수, 1/10000 mil 나머지) 로 나눈다. Altium 처럼 0 쪽 절삭."""
    total = int(round(float(value_mils) * UNITS_PER_MIL))
    whole = abs(total) // UNITS_PER_WHOLE
    if total < 0:
        whole = -whole
    return whole, total - whole * UNITS_PER_WHOLE


def build_pinfrac_stream_for_pins(pins):
    """PinFrac 스트림. 키는 심볼 안 핀 순번의 ASCII 문자열, Altium 이 쓰는 그대로."""
    entries = []
    for idx, pin in enumerate(pins):
        xf = pin.location.x_frac or pin.location_x_frac or 0
        yf = pin.location.y_frac or pin.location_y_frac or 0
        lf = pin.pin_length_frac or 0
        if xf or yf or lf:
            entries.append((str(idx), struct.pack("<iii", xf, yf, lf)))
    if not entries:
        return None
    return encode_auxiliary_stream("PinFrac", entries)


def _apply_pinfrac(schlib, symbol_name, symbol) -> None:
    path = schlib._source_stream_paths_by_fold.get(f"{symbol_name}/PinFrac".casefold())
    if path is None:
        return
    try:
        entries = decode_auxiliary_stream(
            schlib._source_streams[path], expected_header="PinFrac"
        )
    except SchAuxiliaryStreamError:
        # 패치 전 altium_monkey 가 쓴 파일(바이트 키) 등. 핀은 10mil 값 그대로 둔다
        return
    pins = list(symbol.pins)
    for entry in entries:
        if not entry.name.isdigit() or len(entry.data) != 12:
            continue
        idx = int(entry.name)
        if idx >= len(pins):
            continue
        xf, yf, lf = struct.unpack("<iii", entry.data)
        pin = pins[idx]
        pin.location.x_frac, pin.location.y_frac = xf, yf
        pin.location_x_frac, pin.location_y_frac = xf, yf
        pin.pin_length_frac = lf
        pin._length_mils = pin.length * 10.0 + lf / UNITS_PER_MIL


def _install() -> None:
    if getattr(_pin_mod.AltiumSchPin, "_metric_pins_patched", False):
        return
    orig_pin_init = _pin_mod.AltiumSchPin.__init__
    orig_apply_vmargin = _schlib_mod.AltiumSchLib._apply_pin_vertical_margin_data

    def pin_init(self, *args, **kwargs):
        orig_pin_init(self, *args, **kwargs)
        x, y = kwargs.get("x"), kwargs.get("y")
        if kwargs.get("designator") is None or kwargs.get("name") is None:
            return
        if x is None or y is None:
            return
        xw, xf = split_mils(x)
        yw, yf = split_mils(y)
        lw, lf = split_mils(kwargs.get("length", 300))
        self.location.x, self.location.x_frac = xw, xf
        self.location.y, self.location.y_frac = yw, yf
        self.location_x_frac = xf or None
        self.location_y_frac = yf or None
        self._length = lw
        self.pin_length_frac = lf or None
        self._length_mils = lw * 10.0 + lf / UNITS_PER_MIL

    def apply_vmargin(self, symbol_name, symbol, budget):
        orig_apply_vmargin(self, symbol_name, symbol, budget)
        _apply_pinfrac(self, symbol_name, symbol)

    _pin_mod.AltiumSchPin.__init__ = pin_init
    _pin_mod.AltiumSchPin._metric_pins_patched = True
    _aux_mod.build_pinfrac_stream_for_pins = build_pinfrac_stream_for_pins
    _schlib_mod.build_pinfrac_stream_for_pins = build_pinfrac_stream_for_pins
    _schlib_mod.AltiumSchLib._apply_pin_vertical_margin_data = apply_vmargin


_install()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(
        description="SchLib 핀의 정확한 좌표·길이를 찍는다 (PinFrac 포함, 패치 적용 상태).")
    ap.add_argument("schlib", help=".SchLib 파일")
    ap.add_argument("--symbol", help="이 심볼만")
    args = ap.parse_args()

    from altium_monkey import AltiumSchLib

    lib = AltiumSchLib(args.schlib)
    names = [args.symbol] if args.symbol else AltiumSchLib.get_symbol_names(args.schlib)
    for name in names:
        sym = lib.get_symbol(name)
        if sym is None:
            print(f"--- {name}: 없음")
            continue
        print(f"--- {name}  (핀 {len(sym.pins)}개)")
        for p in sym.pins:
            print(f"  {p.designator:>6} {p.name:<12} x={p.x_mils:11.4f} y={p.y_mils:11.4f} "
                  f"len={p.length_mils:9.4f} mil   "
                  f"({p.x_mils * 0.0254:.4f}, {p.y_mils * 0.0254:.4f}, {p.length_mils * 0.0254:.4f} mm)")


if __name__ == "__main__":
    main()
