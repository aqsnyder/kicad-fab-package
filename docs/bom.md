# BOM tools

Three commands work on the bill of materials:

- [`kicad-macrofab-bom`](#kicad-macrofab-bom) writes MacroFab's BOM xlsx, the grouped and per-reference BOM csvs, an
  optional diff against a baseline BOM xlsx, and a checks report.
- [`kicad-bom-check`](#kicad-bom-check) regenerates a commit's grouped BOM csv and compares it with a committed or
  local csv.
- [`kicad-bomdiff`](#kicad-bomdiff) compares two per-reference csvs.

All three read the schematic from a `git archive` copy of the commit, like `kicad-fab-export`.

## kicad-macrofab-bom

```text
kicad-macrofab-bom [REV] --out DIR [options]        (REV defaults to HEAD)
```

Run it before `kicad-fab-export` with `--out <package>/bom`, so the export packs the xlsx into the upload zip and
checks it against the XYRS. Every option is in the [CLI reference](cli.md#kicad-macrofab-bom).

### Files

| File | Contents |
|---|---|
| `NAME_macrofab.xlsx` | the BOM to upload to MacroFab (below) |
| `NAME_bom.csv` | grouped BOM: exactly what [`kicad-bom-check`](#kicad-bom-check) regenerates |
| `NAME_bom_perref.csv` | one line per reference: the input of [`kicad-bomdiff`](#kicad-bomdiff) |
| `NAME_vs_LABEL.md` | per-designator diff against a baseline BOM xlsx (only with a baseline; `LABEL` = `baseline_label`) |
| `NAME_bom_checks.md` | the build record: sources and commands, row rules, counts, the checks, and string-hygiene flags |

### The xlsx

One sheet, a header row, one designator per row in natural order (`C2` before `C10`):

| Column | Contents |
|---|---|
| `Designator` | the reference |
| `Value` | the symbol's Value |
| `Footprint` | the footprint name without its library prefix |
| `Populate` | `1` = fitted, `0` = DNP or excluded from the BOM (a number) |
| `MPN` | the `MPN` field, never the library id; DNP rows keep theirs |
| `Manufacturer` | the `Manufacturer` field, else `MANUFACTURER` |

Leading and trailing whitespace is stripped (and listed in the report); nothing else in a field is changed. Text
cells are shared strings and empty fields are absent cells, like an xlsx MacroFab exports (openpyxl on its own writes
inline strings and empty cells). A value that starts with `=` is written as text, never as a formula. Dates inside
the file are the commit date, so the xlsx of a commit is byte-reproducible for a given openpyxl version.

There is no alternate MPN / Manufacturer pair: alternates are handled on MacroFab's side (see
[the walkthrough](macrofab.md#8-approved-alternates-and-line-priority)).

Rows of the demo's v1.1 xlsx, read back with openpyxl:

```text
('Designator', 'Value', 'Footprint', 'Populate', 'MPN', 'Manufacturer')
('C1', '100uF', 'CP_Axial_L18.0mm_D6.5mm_P25.00mm_Horizontal', 1, 'DEMO-CP-100UF', 'Demo Parts')
('C2', '220uF', 'CP_Axial_L18.0mm_D6.5mm_P25.00mm_Horizontal', 1, 'DEMO-CP-220UF', 'Demo Parts')
('C3', '22uF/25V', 'C_Axial_L12.0mm_D6.5mm_P20.00mm_Horizontal', 1, 'DEMO-C-22UF-25V', 'Demo Parts')
...
('JP1', 'JUMPER', 'SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm', 0, None, None)
...
('R5', '10K', 'R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal', 1, 'DEMO-R-10K-1PCT', 'Demo Parts')
...
('R10', '5,1K', 'R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal', 1, 'DEMO-R-5,1K', 'Demo Parts')
...
```

### Which symbols get a row

- one row per schematic symbol whose footprint is on the board;
- `Populate 1`: in the BOM (not DNP, not excluded from the BOM);
- `Populate 0`: DNP, or excluded from the BOM (test points, programming headers, jumpers, DNP parts);
- no row: fiducials and mounting holes (Populate 0, no MPN, and a designator matching
  [`non_part_refs`](configuration.md#non_part_refs) or a footprint library in
  [`non_part_libs`](configuration.md#non_part_libs)), board-only footprints without a symbol (logos), and symbols
  excluded from the board. `kicad-fab-export` leaves exactly the same parts out of the XYRS.

**Give every DNP part "Exclude from bill of materials" too.** kicad-cli (10.0.7) drops excluded-from-BOM symbols
from every BOM export, while a DNP symbol that is still in the BOM is exported with its DNP column set. The tool
stops on such a part ([example](troubleshooting.md#dnp-but-still-in-the-bom)), because the grouped csv and the
export's `Populate 1` check expect DNP parts outside the BOM.

### Checks

The command exits 1 when any of these fails (the files are still written):

- the schematic and the board have the same designators (every symbol has a footprint, every footprint with pads has
  a symbol, no duplicates, nothing unannotated);
- per row, the schematic and the board footprint agree on footprint, Value, MPN, DNP and Exclude-from-BOM (else:
  *Update PCB from Schematic?*);
- no footprint of a row is excluded from position files (the XYRS would lack it);
- the kicad-cli BOM export agrees with the netlist;
- every `Populate 1` row has an MPN;
- `--expect-fitted N`: exactly N rows have Populate 1; `--expect-unfitted REFS`: the Populate 0 designators are
  exactly `REFS` (a comma list; ranges like `TP1-TP8` work);
- a configured baseline exists (when `baseline_paths` is set and none of the paths exists at `REV`).

A commit on no branch or tag gives a `WARNING`, because its hash goes into the xlsx properties and the reports.

### The checks report

`NAME_bom_checks.md` repeats the commands used, the row rules, counts per side, the Populate 0 rows and the parts
with no row, the checks, and these **flags** (reported, never fixed for you):

| Flag | Why it matters |
|---|---|
| Whitespace stripped | a stray space can make two identical parts different lines |
| MPNs with commas, slashes or other unusual characters | often a typo, or two MPNs in one field; each is compared with the baseline's MPN for that designator |
| Non-ASCII or control characters | the XYRS is ASCII-only, and `kicad-fab-export` fails a check on them |
| Double spaces | as whitespace |
| Cells starting with `=` | written as text, not formulas |
| Fitted rows with DNP / DNM inside Value, MPN or Footprint | MacroFab's BOM rules (a 2016 announcement) turn population off when Value or MPN contains DNP / DNM; check those parts stay populated after the import |
| MacroFab house parts (`MF-`) | kept as in the schematic; listed so you know which lines MacroFab supplies from its house stock |
| Fitted rows without a Manufacturer; Manufacturer from the `MANUFACTURER` fallback | missing or inconsistently named fields |
| Populate 0 rows without an MPN | normal for jumpers and test points; a DNP part keeps its MPN |
| Manufacturer names, and name variants | the same maker spelled two ways (`Demo Parts`, `Demo Parts Inc.`) can confuse sourcing |
| Manufacturer names MacroFab spells differently | a known rename (for example *CUI Devices* is listed as *Same Sky*) |
| Same MPN under different Manufacturer names | as name variants |
| Value + footprint collisions | MacroFab groups BOM lines by Value + package: fitted rows with the same Value and footprint but different MPNs could be merged into one line with one MPN |
| Value + footprint groups that mix fitted and Populate 0 rows | if a grouped line carried one Populate for all its designators, a DNP part would be fitted or fitted parts dropped |

From the demo's v1.1 report:

```text
### MPNs with commas, slashes or other unusual characters (1)

| Designator | MPN | Characters | As-built v1.0 |
|---|---|---|---|
| R10 | `DEMO-R-5,1K` | `,` | baseline MPN `DEMO-R-5-1K` |
...
### Value + footprint collisions (MacroFab groups BOM lines by Value + package) (1)

| Value | Footprint | MPN: designators |
|---|---|---|
| 10K | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | DEMO-R-10K: R1-R4, R6-R7; DEMO-R-10K-1PCT: R5 |

After the import, check that each of these designators keeps its own MPN (Ungroup / New Group in MacroFab's BOM tab if not).
```

### The mixed-Populate report

In v1.0 of the demo, `R21` is a DNP 470 ohm resistor with the same Value and footprint as the fitted `R12`-`R14`:

```text
### Value + footprint groups that mix fitted and Populate 0 rows (1)

| Value | Footprint | Populate 1 | Populate 0 |
|---|---|---|---|
| 470 | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | R12-R14 | R21 |

After the import, check every Populate 0 designator above by name: it must stay Do Not Place, and the fitted ones must stay fitted (Ungroup if MacroFab merged the line).
```

This is the classic "only some of the 0 ohm straps are fitted" case. The xlsx is right (one row per designator, each
with its own Populate); the risk is in how the line is grouped after the import, so check it there. See
[line grouping and Populate](macrofab.md#7-line-grouping-and-populate).

### Diffing against a baseline BOM

Give a baseline (the BOM xlsx of the last build, as uploaded or as MacroFab exported it) to get
`NAME_vs_LABEL.md`:

- `--baseline REV:PATH` reads a committed file with `git show` (`PATH` repo-relative);
- `--baseline FILE` reads a local file;
- or set `baseline_paths` (project-relative, the first one that exists at `REV` wins) and `baseline_label` in the
  config file; `--no-baseline` skips it.

The demo repository's `kicad-fab.toml` has `baseline_paths = ["release/pic_programmer_v1.0_macrofab.xlsx"]` and
`baseline_label = "v1.0"`, so the v1.1 BOM is diffed without any flag:

```text
$ kicad-macrofab-bom v1.1 --out ../fab/v1.1/bom
rev v1.1 = b483688d2 (pic_programmer 1.1: R18 330R, R21 fitted, R5/R10 MPNs), kicad-cli 10.0.7, NAME pic_programmer_v1.1
commit on: refs/heads/main, refs/tags/v1.1
rows 57: Populate 1 = 56 (F 56 / B 0), Populate 0 = 1: JP1
no row: P101-P106; board-only footprints: 0
flags: odd MPNs ['R10 DEMO-R-5,1K']; MF- house parts 1 MPNs; DNP text on fitted rows -; manufacturer variants [['Demo Parts', 'Demo Parts Inc.']]; value+footprint collisions 1; mixed-Populate groups 0; whitespace stripped 0
vs v1.0: added 0, removed 0, changed 5 (MPN 3, Manufacturer 1, Populate 1)
wrote: pic_programmer_v1.1_macrofab.xlsx, pic_programmer_v1.1_bom.csv, pic_programmer_v1.1_bom_perref.csv, pic_programmer_v1.1_vs_v1.0.md, pic_programmer_v1.1_bom_checks.md -> ../fab/v1.1/bom
CHECKS PASSED
```

`pic_programmer_v1.1_vs_v1.0.md`, trimmed:

```text
# pic_programmer_v1.1 BOM vs the as-built v1.0 BOM
...
## Changed (5)

Only the changed fields are filled (v1.0 -> v1.1).

| Designator | Populate | MPN | Manufacturer | Value | Footprint | Note |
|---|---|---|---|---|---|---|
| R5 |  | DEMO-R-10K -> DEMO-R-10K-1PCT |  |  |  |  |
| R10 |  | DEMO-R-5-1K -> DEMO-R-5,1K |  |  |  |  |
| R18 |  | DEMO-R-220 -> DEMO-R-330 |  | 220 -> 330 |  |  |
| R21 | 0 -> 1 |  |  |  |  |  |
| U1 |  |  | Demo Parts Inc. -> Demo Parts |  |  |  |

## MPNs on fitted rows that the v1.0 BOM does not have (3)

Stock-check these first: they were never bought for this board.

| MPN | Manufacturer | Designators |
|---|---|---|
| DEMO-R-10K-1PCT | Demo Parts | R5 |
| DEMO-R-5,1K | Demo Parts | R10 |
| DEMO-R-330 | Demo Parts | R18 |

## v1.0 fitted MPNs no longer on the BOM (2)
...
```

The diff compares Populate, MPN, Manufacturer (the baseline's first pair), Value and Footprint per designator;
"MPN format only" marks MPNs that are equal once case, spaces and hyphens are ignored. A baseline with second MPN /
Manufacturer columns gets those listed as its alternates. `revision_label` (default `v{revision}`) names the new
build in the text.

## kicad-bom-check

```text
kicad-bom-check [REV] [--csv PATH | --against FILE] [--out DIR] [--perref]
```

Regenerates the **grouped** BOM csv of `REV` with one fixed kicad-cli command and compares it with a committed csv
(`--csv PATH`, read at `REV`; or the `bom_csv` config key) or a local file (`--against FILE`). The comparison ignores
CR, since a working copy may be CRLF while the committed blob is LF. Exit 0 identical, 1 different, 2 error. With
nothing to compare with, `--out DIR` exports only.

The recipe:

```text
kicad-cli sch export bom --fields 'Reference,${QUANTITY},Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}'
  --labels 'Reference,Qty,Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,DNP'
  --group-by 'Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}'
  -o <csv> <project>.kicad_sch
```

Field names are case-sensitive: a schematic with no `Voltage` field gets an empty column, and one spelling it
`Tempco` gets an empty `TempCo`. `kicad-macrofab-bom` writes `NAME_bom.csv` with the same command, so the two always
agree:

```text
$ kicad-bom-check v1.1 --against ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv
rev v1.1 = b483688d2: regenerated 38 lines, local 38 lines
BOM: identical to ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv (CR ignored)
```

Commit the grouped csv with the design and CI (or a pre-commit hook) can tell when someone changed the schematic
without updating it:

```text
$ kicad-bom-check HEAD --csv hw/release/pic_programmer_bom.csv
rev HEAD = 65451ff34: regenerated 38 lines, committed 38 lines
BOM: identical to the committed csv (CR ignored)
```

A difference prints a unified diff (`-` the csv you gave, `+` regenerated) and exits 1. Comparing v1.0's schematic
against the v1.1 csv:

```text
$ kicad-bom-check v1.0 --against ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv
rev v1.0 = 8d621b050: regenerated 37 lines, local 38 lines
BOM: DIFFERS from ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv: 9 changed lines
    --- local
    +++ regenerated
    @@ -22,2 +22 @@
    -"R1-R4,R6,R7","6","10K","Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal","DEMO-R-10K","","","","",""
    -"R5","1","10K","Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal","DEMO-R-10K-1PCT","","","","",""
    +"R1-R7","7","10K","Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal","DEMO-R-10K","","","","",""
...
```

`--perref --out DIR` also writes the per-reference csv, the input of `kicad-bomdiff`:

```text
$ kicad-bom-check v1.0 --perref --out ../bomdiff/v1.0
rev v1.0 = 8d621b050: regenerated 37 lines (no csv to compare with: export only)
outputs in ../bomdiff/v1.0
```

Files: `<rev>.grouped.csv` and `<rev>.perref.csv` (a `/` in `REV` becomes `_`).

Excluded-from-BOM parts are in neither csv (kicad-cli drops them); the MacroFab xlsx adds them as Populate 0 rows.

## kicad-bomdiff

```text
kicad-bomdiff A.perref.csv B.perref.csv
```

A per-reference diff of two per-reference csvs: references added and removed (with value, footprint, MPN, DNP) and,
for references on both sides, every field that changed. It compares Value, Footprint, MPN, Manufacturer, Voltage,
Type, Tolerance, TempCo, DNP, ExclBOM and ExclBoard, but only the columns both files have; a column only one file has
is named in a `NOTE` line, so an older export without, say, `Manufacturer` does not report every reference as
changed. A `Tempco` column is read as `TempCo`. It needs no KiCad and no git.

```text
$ kicad-bomdiff ../bomdiff/v1.0/v1.0.perref.csv ../bomdiff/v1.1/v1.1.perref.csv
refs A=55 B=56
ADDED (1):
  + R21    470        Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal DEMO-R-470
REMOVED (0):
CHANGED (4):
  ~ R5     MPN: 'DEMO-R-10K' -> 'DEMO-R-10K-1PCT'
  ~ R10    MPN: 'DEMO-R-5-1K' -> 'DEMO-R-5,1K'
  ~ R18    Value: '220' -> '330'; MPN: 'DEMO-R-220' -> 'DEMO-R-330'
  ~ U1     Manufacturer: 'Demo Parts Inc.' -> 'Demo Parts'
```

`R21` shows as added because a DNP part excluded from the BOM is not in kicad-cli's BOM export; the xlsx diff above
shows the same change as `Populate 0 -> 1`.

It exits 0 whenever it could compare the two files, whatever it found. A missing or unreadable file, a csv with no
`Reference` column, or a grouped BOM (where one line lists several references) is a setup error, exit 2:

```text
$ kicad-bomdiff ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv ../bomdiff/v1.1/v1.1.perref.csv
ERROR: ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv: a grouped BOM (Reference 'C6,C7'); kicad-bomdiff reads per-reference csvs, as `kicad-bom-check REV --perref --out DIR` writes them
```
