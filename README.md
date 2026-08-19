# altium-claude-skills

English | [한국어](README.ko.md)

Claude Code skills for Altium hardware design.
Three stages: library authoring, schematic review, PCB placement.

Written while taking one real board (175 components) from schematic review through
placement, so the traps are the ones that actually bite — each stated as a rule with
the measured number behind it.

> **The skill bodies are written in Korean.** Only the `description` fields are
> bilingual. This is deliberate — those files are read by the model, which handles
> Korean fine, and keeping two translated copies in sync would rot. If you need
> English bodies, translate them once and keep only that copy.

| Skill | What it does |
|---|---|
| `altium-library` | Build and verify symbols (.SchLib) / footprints (.PcbLib) as code, including measuring datasheets and 2D drawings |
| `altium-schematic-review` | Review a schematic — find unconnected pins, missing footprints, net errors; judge each against the datasheet |
| `altium-pcb-placement` | Board size, IC/connector rotation, placement plan drawing, coordinate injection, overlap check |

## What is actually in here

Each skill is a `SKILL.md` (the procedure) plus `references/` (the traps, in detail)
and `scripts/`. The reference files are where most of the hard-won part lives —
about 1,400 lines of "this is how it breaks and how you tell".

| File | What it saves you from |
|---|---|
| `altium-library/references/altium-monkey-api.md` | Unit conventions (input mil, read-back 10-mil), z-order making pin names invisible, parameters written to the wrong coordinate |
| `altium-library/references/tool-traps.md` | Where `altium-mcp` / `eda-agent` misbehave, and what a wrong result looks like |
| `altium-library/references/drawing-measurement.md` | Vendor drawings store text as vector outlines; pixel-eyeballing a render is wrong three times out of three |
| `altium-schematic-review/references/pin-verdict.md` | Deciding whether a floating pin is actually a defect |
| `altium-schematic-review/references/altium-script-traps.md` | `run_altium_script` halting in the debugger and blocking every MCP tool |
| `altium-schematic-review/references/net-build-notes.md` | Why a geometric netlist disagrees with Altium's compiler |
| `altium-pcb-placement/references/rotation-decision.md` | Deriving IC rotation from pin-to-side mapping; connector opening direction |
| `altium-pcb-placement/references/board-sizing.md` | Back-calculating board size; symmetric mounting holes; corner radius |
| `altium-pcb-placement/references/injection.md` | Component origin is not the bbox centre; the authoring builder swallowing direct edits |
| `altium-pcb-placement/references/plan-schema.md` | The `plan.json` format, with a working example in `examples/` |

## Install

Clone, then link the skill folders into `~/.claude/skills/` with directory
junctions. Junctions need no admin rights on Windows.

```powershell
git clone https://github.com/letjsk/altium-claude-skills.git `
    C:\path\to\altium-claude-skills

$repo = "C:\path\to\altium-claude-skills"
foreach ($s in 'altium-library','altium-pcb-placement','altium-schematic-review') {
    New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\$s" -Target "$repo\$s"
}
```

**Junctions bake an absolute path.** Move the repo and you must recreate them.
If you would rather not use junctions, just copy the three folders into
`~/.claude/skills/` — but then `git pull` will not reach them.

## Skill interdependency

`altium-pcb-placement/scripts/connectivity_matrix.py` imports `net_erc.py` from
`altium-schematic-review` via a sibling-folder relative path.
**Install those two together.**

## Requirements

### Altium Designer

Windows. File-parsing steps work with Altium closed. Placement, screenshots and
live library queries need it open.

### Python 3.12 + `altium_monkey`

Most scripts read Altium files (`.SchDoc` `.PcbDoc` `.PcbLib` `.SchLib`) **directly**
with [`altium_monkey`](https://github.com/wavenumber-eng/altium_monkey), so Altium
does not have to be running. That package requires Python `<3.13`.

```powershell
# 1. install Python 3.12 if you do not have it, then make a venv for this
py -3.12 -m venv C:\tools\edatools

# 2. install the two packages
C:\tools\edatools\Scripts\python.exe -m pip install altium-monkey pymupdf

# 3. check
C:\tools\edatools\Scripts\python.exe -c "import altium_monkey, pymupdf; print('ok')"
```

Run every script with **that venv's `python.exe`**, by full path. The skills refer
to it as `python`; do not assume the `python` on your PATH is the right one.

`pymupdf` measures datasheets and 2D drawings — vendor drawings store text as
vector outlines, so they must be rendered and read, not text-extracted.

### MCP: `altium-mcp`

Drives a running Altium. Needed for **placement** (`place_components`), screenshots,
and live library queries. Without it, everything that only touches files still works —
parsing, measurement, rotation calculation, plan drawings, overlap checks.

```powershell
git clone https://github.com/coffeenmusic/altium-mcp.git C:\tools\altium-mcp

claude mcp add altium-mcp --scope user -- `
    C:\tools\edatools\Scripts\python.exe C:\tools\altium-mcp\start_server.py
```

The server bootstraps its own venv on first call, and installs a script project into
Altium. Verify with `claude mcp list`, then ask Claude to call `get_server_status`.

> Its own README documents the Claude **Desktop** route (a `.dxt` extension).
> For Claude **Code**, use `claude mcp add` as above.

### MCP: `pcbparts` (optional)

Part specs and stock (`jlc_search`), general design rules (`get_design_rules`).
Hosted, no install:

```powershell
claude mcp add --transport http pcbparts --scope user https://pcbparts.dev/mcp
```

Without it, get the same from datasheets or the web (`WebSearch` / `WebFetch`,
built into Claude Code).

### Do not run `eda-agent` with `altium-mcp`

**Altium has exactly one global scripting slot.** `eda-agent` needs its own polling
loop inside Altium, and starting it kills the `altium-mcp` bridge.

Two **optional** steps in `altium-library` (3D models) call `eda-agent` tools
(`lib_extract_cse_zip`, `lib_easyeda_import`). To use them, stop `altium-mcp`, run
`eda-agent`, then switch back. Both steps have a manual fallback.

For the same reason `run_altium_script` is used sparingly: a runtime error leaves
the script halted in Altium's debugger, which blocks *every* MCP tool until a human
presses `Ctrl+F3`.

## What works without Altium

| | Needs Altium | Files only |
|---|---|---|
| Library authoring | visual check | generate, diff, measure |
| Schematic review | compiled net cross-check (optional) | net build, ERC-like checks, footprint audit |
| PCB placement | **coordinate injection**, screenshots | measure, rotation calc, plan drawing, overlap check |

**A placement plan for an outside PCB design house can be made without Altium** —
a schematic plus a library (or just datasheets) is enough.

## Contributing

Issues and PRs welcome. Two things keep these usable:

- **Write rules backed by measured numbers**, not incident reports.
  `QFN32 body 4.00 → actual footprint 7.05×7.00` is information
- **No specific chip or board names, and no values from one design.**
  These are general skills; judgement comes from the datasheet each time

## License

[MIT](LICENSE)
