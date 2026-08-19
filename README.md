# altium-claude-skills

English | [한국어](README.ko.md)

Claude Code skills for Altium hardware design.
Three stages: library authoring, schematic review, PCB placement.

Built while taking one real board (175 components) from schematic review through
placement. The traps hit along the way are written into the skills, with the
measured numbers that back them.

> **The skill bodies are written in Korean.** Only the `description` fields are
> bilingual. This is deliberate — those files are read by the model, which handles
> Korean fine, and keeping two translated copies in sync would rot. If you need
> English bodies, translate them once and keep only that copy.

| Skill | What it does |
|---|---|
| `altium-library` | Build and verify symbols (.SchLib) / footprints (.PcbLib) as code, including measuring datasheets and 2D drawings |
| `altium-schematic-review` | Review a schematic — find unconnected pins, missing footprints, net errors; judge each against the datasheet |
| `altium-pcb-placement` | Board size, IC/connector rotation, placement plan drawing, coordinate injection, overlap check |

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

### 1. Altium Designer

Windows. Anything that only parses files works without Altium running, but
placement, screenshots and live library queries need it open.

### 2. Python + `altium_monkey`

Most scripts parse Altium files (`.SchDoc` `.PcbDoc` `.PcbLib` `.SchLib`)
**directly** with [`altium_monkey`](https://github.com/wavenumber-eng/altium_monkey),
so Altium does not have to be running.

That package requires Python `<3.13`, so keep a **3.12 virtualenv**:

```powershell
py -3.12 -m venv C:\tools\edatools
C:\tools\edatools\Scripts\pip install altium-monkey pymupdf
```

The skills call this interpreter `python`. Run the scripts with **that venv's
python.exe**.

`pymupdf` is used to measure datasheets and 2D drawings — vendor drawings store
text as vector outlines, so they have to be rendered and read, not extracted.

### 3. MCP servers

| MCP | Used for | Without it |
|---|---|---|
| [`altium-mcp`](https://github.com/coffeenmusic/altium-mcp) | **Placement** (`place_components`), screenshots, library symbol/footprint queries, reading the open board | `altium-pcb-placement` loses coordinate injection and visual verification. Everything else (file parsing, calculation, plan drawing) still works |
| `pcbparts` | Part specs and stock (`jlc_search`), general design rules (`get_design_rules`) | Optional — find the same from datasheets or the web |

`WebSearch` / `WebFetch` (built into Claude Code) are used when a datasheet is not
available locally.

**Do not run `eda-agent` alongside this.** It needs its own polling loop inside
Altium, and **Altium has exactly one global scripting slot** — starting it kills
the `altium-mcp` bridge. For the same reason `run_altium_script` is used sparingly:
a runtime error leaves the script halted in the debugger, which blocks *every* MCP
tool until a human presses `Ctrl+F3`.

### 4. Nothing to install

The 3D-model section pulls from KiCad packages3D and EasyEDA. Internet access is
all that is needed.

## What works without Altium

| | Needs Altium | Files only |
|---|---|---|
| Library authoring | visual check | generate, diff, measure |
| Schematic review | compiled net cross-check (optional) | net build, ERC-like checks, footprint audit |
| PCB placement | **coordinate injection**, screenshots | measure, rotation calc, plan drawing, overlap check |

**A placement plan for an outside PCB design house can be made without Altium** —
a schematic plus a library (or just datasheets) is enough.

## When editing

- **Write rules, and back them with measured numbers.** Do not write up incidents
  as stories. `QFN32 body 4.00 → actual footprint 7.05×7.00` is information;
  "I once guessed 4×4 and was wrong" is somebody's diary. Keep the former
- **Do not copy scripts into a project folder.** Forks drift, and the stale copy
  keeps running
- **No specific chip or board names, and no values from one design.** These skills
  are general. Judgement comes from reading the datasheet each time

## License

[MIT](LICENSE)
