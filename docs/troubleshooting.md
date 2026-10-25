# Troubleshooting and FAQ

Most of the messages below are real: they come from running the tools on KiCad's `pic_programmer` demo exactly as
KiCad ships it (`~/boards/pic_programmer_raw`), or on scratch commits of the prepared demo (see
[the examples](index.md#the-examples-in-these-pages)). Local paths are shortened.

The unmodified demo's export ends like this; the sections below take the problems one at a time:

```text
$ kicad-fab-export HEAD --out ../raw --name pic_programmer_raw --work ../w/raw
...
  ok   gerbers                9 Gerbers from the pinned-flag plot (X1 forced); gbrjob cut to them; pinned-flag plot DIFFERS
...
  WARN board plot params: X2 attributes off (usegerberattributes no)  -- usegerberattributes=yes
  WARN board plot params: netlist attributes off (usegerberadvancedattributes no)  -- usegerberadvancedattributes=yes
  WARN gerbers: --board-plot-params output identical to the pinned flags (--no-x2 --no-netlist --no-protel-ext --precision 6)  -- differ: pic_programmer-top_layer.gbr (not written by both plots), ...
  FAIL XYRS: board and schematic agree (DNP, BOM exclusion, value, footprint, MPN; MPN on fitted parts; ASCII)  -- C1 fitted with no MPN; C1 value '100µF' is not printable ASCII; C2 fitted with no MPN; ...
  FAIL assembly PDF: every XYRS designator is printed on its side's page (57)  -- missing P3 RV1 JP1
  FAIL STEP: every placed part with a model entry gets a model  -- P3 RV1
  WARN iBOM: skipped (no --ibom-pkg)
...
NOTE: X2/netlist attributes were ON in the board plot settings: the fab Gerbers come from the explicit --no-x2 --no-netlist plot (X1), not from --board-plot-params
...
RESULT: FAILED (3 failed steps/checks); work folder kept: ~/boards/w/raw
```

## Setup errors (exit code 2)

### No usable NAME

```text
$ kicad-macrofab-bom HEAD --out ../raw/bom
ERROR: no REVISION text variable in the project: pass --name
```

The default name template is `{project}_v{revision}` and the project has no `REVISION`. Define a `REVISION` text
variable (and save the board so the `.kicad_pcb` carries it as a property: `kicad-fab-export` reads the board), pass
`--name`, or set a [`name_template`](configuration.md#name_template) without `{revision}`. `kicad-fab-export` says
`no usable NAME (board property REVISION=''); pass --name` for the same thing.

### kicad-cli or KiCad's Python not found

```text
$ KICAD_CLI=../nokicad/kicad-cli kicad-bom-check v1.1 --against ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv
ERROR: kicad-cli not found: ../nokicad/kicad-cli (use --kicad-cli or KICAD_CLI)
$ KICAD_PYTHON=../nokicad/python3 kicad-fab-export v1.1 --out ../t3
ERROR: KiCad python not found: ../nokicad/python3 (--kicad-python, KICAD_PYTHON or KICAD10_PYTHON)
```

A path given by flag, environment or config file is used as it is, without auto-detection; check it. With nothing
given and nothing found, the message is `kicad-cli not found in the standard install folders or on PATH`. KiCad's
Python must be the one bundled with KiCad (it is the one that can `import pcbnew`); on Linux distributions that
package KiCad's Python module for the system Python, that is usually `/usr/bin/python3`.

### A kicad-cli older than KiCad 10

```text
$ kicad-bom-check v1.1 --kicad-cli "<KiCad 9.0>/bin/kicad-cli.exe" --against ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv
WARNING: <KiCad 9.0>/bin/kicad-cli.exe is KiCad 9.0.8; these tools are written for KiCad 10 (board format, kicad-cli options). Point --kicad-cli or KICAD_CLI at a KiCad 10 kicad-cli.
ERROR: BOM export failed:

Failed to load schematic
```

KiCad 9 cannot read a KiCad 10 schematic. When several KiCad versions are installed, auto-detection takes the newest
standard install before `PATH`, so this usually only happens with an explicit path.

### Cannot auto-detect the project folder

```text
$ kicad-macrofab-bom HEAD --out ../t4
ERROR: cannot auto-detect the project folder: 0 .kicad_pro files with a .kicad_pcb beside them (none); pass --project-dir
```

The repository has no committed project (or several). Pass `--project-dir`, or set
[`project_dir`](configuration.md#project_dir). Remember the tools read the commit, not the working tree: a project you
have not committed does not exist for them.

### Not a git repository

```text
$ kicad-bom-check HEAD --repo empty_dir --csv x.csv
ERROR: git rev-parse --verify HEAD^{commit}: fatal: not a git repository (or any of the parent directories): .git
```

Run from inside the repository or pass `--repo`.

### The output folder is not empty

```text
$ kicad-fab-export v1.1 --out ../fab/v1.1
ERROR: ~/boards/fab/v1.1/fab is not empty (use --force to overwrite same-named files)
```

`--force` overwrites same-named files and lists the other files it found; a fresh folder per release is cleaner.

### Config file errors

Unknown keys, wrong types and bad templates stop the run before anything else; see
[Configuration](configuration.md#the-config-file) for the messages. On Python 3.9 or 3.10 without `tomli`, a
`kicad-fab.toml` gives `reading TOML needs Python 3.11+ or the tomli package (pip install tomli), or use a JSON config
file`: install the `[toml]` extra or switch to `kicad-fab.json`.

## Check failures (exit code 1)

### Populate 1 without an MPN

```text
$ kicad-macrofab-bom HEAD --out ../raw/bom --name pic_programmer_raw
...
ERROR: C1: Populate 1 without an MPN
ERROR: C2: Populate 1 without an MPN
...
CHECKS FAILED
```

and in the export, `FAIL XYRS: board and schematic agree ... -- C1 fitted with no MPN; ...`. Every fitted part needs
an `MPN` field (case-sensitive), on the symbol and, after Update PCB from Schematic, on the footprint. The library
symbol's name is never used as the MPN. Parts you do not buy (test points, jumpers) should be *Exclude from bill of
materials*; fiducials and mounting holes are left out entirely by [`non_part_refs`](configuration.md#non_part_refs) /
[`non_part_libs`](configuration.md#non_part_libs).

### Non-ASCII characters in a value

```text
FAIL XYRS: board and schematic agree (...)  -- ...; C1 value '100µF' is not printable ASCII; ...
```

The XYRS is ASCII; the export still writes it, with `?` in place of the character, so you see every other problem in
the same run:

```text
C1	957.87	2395.00	180	1	2	1078.74	94.49	100?F	CP_Axial_L18.0mm_D6.5mm_P25.00mm_Horizontal	1
```

Write `100uF` instead (in the schematic, then Update PCB). Never upload an XYRS from a failed run.

### X2 attributes and Protel extensions

The three `WARN` lines and the `NOTE` at the top of this page: the demo's plot settings have Gerber X2 and netlist
attributes on, and Protel file extensions on. The export does not fail: it uses the explicit `--no-x2 --no-netlist`
plot for the fab Gerbers, and the cross-check between the two plots reports every file as `(not written by both
plots)`, because one plot wrote `.gtl`-style names and the other `.gbr`. Fix it once in KiCad's Plot dialog (X2 off,
netlist attributes off, Protel extensions off) and save the board; the warnings go away and the files come from your
own settings again.

### Fab layer set incomplete

A scratch commit whose plot settings select only the copper layers:

```text
$ kicad-fab-export HEAD --out ../scratch1 --work ../w/scratch1
...
steps:
  FAIL gerbers                fab layer set incomplete: {'Copper': 2}
  SKIP drill                  needs gerbers
  SKIP paste on unplaced parts needs gerbers
...
  FAIL gerbers: 2 copper + 7 fab layers in the gbrjob  -- {'Copper': 2}
...
  WARN source commit is on a branch or tag (its hash and subject go into the XYRS header, the manifest and the zip dates)  -- commit 112228923 is on NO branch or tag: a scratch commit. Do not commit these outputs; re-run on the final commit
...
RESULT: FAILED (2 failed steps/checks); work folder kept: ~/boards/w/scratch1
```

The Gerbers come from the board's own plot settings, so they must select every copper layer, F/B.Mask, F/B.Paste,
F/B.Silkscreen and Edge.Cuts. Select them in the Plot dialog and save the board. Steps that need the Gerbers are
skipped; the others still ran and their outputs are in `--out`.

### Designators missing on the assembly drawing

```text
FAIL assembly PDF: every XYRS designator is printed on its side's page (57)  -- missing P3 RV1 JP1
```

These footprints have no `${REFERENCE}` text on their Fab layer (F.Fab, or B.Fab for a bottom part), so the assembly
drawing does not say what they are. Add a reference text on the Fab layer in the footprint (KiCad's standard
footprints have one). The check needs PyMuPDF (without it the summary has the warning
`assembly PDF: designators not checked (no PyMuPDF)`); it runs whether or not `pypdf` merged the two pages.

### Parts with no 3-D model

```text
FAIL STEP: every placed part with a model entry gets a model  -- P3 RV1
```

Every model entry of these footprints points at a file that does not exist (here
`${KIPRJMOD}/libs/3d_shapes/textool_40.wrl`, which the demo does not ship). Fix the path, add the file (for a library
submodule, set [`library_dir`](configuration.md#library_dir)), or remove the entry; a footprint with no model entry
at all is only a warning (`STEP: fitted parts with no 3-D model in their footprint`).

### DNP but still in the BOM

A scratch commit where `R20` is DNP but not excluded from the BOM:

```text
$ kicad-macrofab-bom HEAD --out ../scratch2/bom --no-baseline
rev HEAD = 0997539f2 (try: R20 DNP only), kicad-cli 10.0.7, NAME pic_programmer_v1.1
commit on: NO branch or tag
WARNING: 0997539f2 is on no branch or tag (a scratch commit): its hash is in the xlsx properties and the reports; re-run on the final commit before committing these files
...
ERROR: R20: DNP but still in the BOM (in_bom yes), so kicad-cli exports it with DNP set; give it Exclude from BOM as well, like the other DNP parts (the grouped csv and kicad-fab-export expect DNP parts outside the BOM)
ERROR: R20: in the BOM export although DNP / excluded from the BOM
...
CHECKS FAILED
```

Set *Exclude from bill of materials* on every DNP symbol (and Update PCB). The part keeps its MPN and becomes a
`Populate 0` row.

### Paste on a part that is not placed

The demo has no SMT part that is not placed, so there is no real output here; the two checks are named
`paste: no paste in the board on the N Populate 0 parts (...)` and
`paste: no paste flash, region or draw inside a Populate 0 part's pad box (its own side)`, and their detail names the
part and what carries the paste.

A DNP (or excluded-from-BOM) SMT part still has pads on F.Paste / B.Paste, or footprint graphics on a paste layer
(an exposed-pad paste window is the usual one; the detail names it by uuid), so the stencil would print paste where
nothing will be placed. Remove the paste from that footprint instance (pad layers, or the graphic), or use a
footprint variant without paste. When the board cannot change before the order, `--accept-dnp-paste REF1,REF2` turns
the error into a warning and a `NOTE`; then tell MacroFab "no paste at REF1, REF2" in the
[DFM email](macrofab.md#the-dfm-email).

### An expected count changed

```text
$ kicad-fab-export v1.1 --out ../expect --no-zip --expect fitted=55,filled=4 --work ../w/expect
...
  FAIL expect fitted = 55  -- got 56
...
RESULT: FAILED (1 failed steps/checks); work folder kept: ~/boards/w/expect
```

A count you pinned with `--expect` changed: either the design changed on purpose (update the pinned count after
reviewing the change) or something you did not expect happened (find out what).

### The xlsx and the XYRS disagree

A package folder whose `bom/` holds an xlsx from another commit:

```text
$ kicad-fab-export --zip-only --out fab_mismatch
ok    upload zip: member names are flat, start with pic_programmer_v1_0 and have exactly one dot (before the extension)
FAIL  xlsx vs XYRS: same designators (57), unique, same Populate - only xlsx []; only XYRS []; duplicates 0; Populate differs ['R21']
ERROR: the xlsx and the XYRS disagree: upload zip NOT written (the existing pic_programmer_v1.0_macrofab_upload.zip is now out of date)
```

Run `kicad-macrofab-bom` and `kicad-fab-export` on the same commit. The zip is not written while they disagree, and
an older zip in the folder no longer matches its contents.

### A scratch commit

`source commit is on a branch or tag ... is on NO branch or tag: a scratch commit` (export) and
`WARNING: ... is on no branch or tag` (BOM) are warnings. Exporting a detached commit is fine for trying things;
keep only outputs made from a commit that is on a branch or tag, because the commit hash is written into the XYRS
header, the manifest, the xlsx properties and the zip dates.

## FAQ

**Can I export the working tree, uncommitted?** No: the package always describes a commit. Commit to a scratch branch
(or make a detached commit) to try something; the scratch-commit warning reminds you not to keep those outputs.
`kicad-project-copy DEST --worktree` copies the working tree if you only want a checked project copy.

**Where did the temporary work folder go?** On success it is deleted. On failure, or with `--keep-work` / `--work
DIR`, it is kept and the summary names it; it holds the project copy, both Gerber plots, KiCad's drill output, the
pcbnew dump and the intermediate PDFs. Delete it yourself.

**Why is `NAME_PTH_FILLED.drl` empty?** The board has no vias with `(filling yes) (capping yes)`. That is fine for most
boards; set [`require_filled_vias`](configuration.md#require_filled_vias) if yours must have them.

**Why do my Gerbers differ from yesterday's when nothing changed?** KiCad writes the creation time into Gerbers,
drill files, the job file and the PDFs. Everything else (XYRS, position file, layer map, BOM xlsx and csvs, reports) is
byte-identical for the same commit; compare the manifest's `outputs` hashes.

**Why is pin 1 of a bottom-side part in the wrong place in MacroFab's viewer?** The XYRS uses MacroFab's own rule
(bottom = KiCad orientation + 180); a footprint whose pin 1 is not where its orientation suggests needs a look. The
manifest's `xyrs_pad1` gives every part's pad-1 offset as seen from the top, to compare with what the viewer shows.
See [XYRS](xyrs.md#placement-review-data).

**Do I need the `[pdf]` extra?** No, but without it the summary says what was not done. With neither `pypdf` nor
PyMuPDF installed (the demo's v1.1, Python 3.9):

```text
  ok   assembly PDF           two files (no pypdf)
...
  WARN assembly PDF: pypdf missing, written as two files
  WARN assembly PDF: designators not checked (no PyMuPDF)
```

With PyMuPDF but no `pypdf`, the drawing stays two files and the designator check runs on them:

```text
  ok   assembly PDF           two files (no pypdf), all 57 designators found
...
  WARN assembly PDF: pypdf missing, written as two files
  ok   assembly PDF: every XYRS designator is printed on its side's page (57)
```

**Two exports at once?** Do not run two exports at the same time on one machine: concurrent `kicad-cli` ODB++ exports
have been seen to write an incomplete archive.

**Windows: `Filename too long`.** git (and some tools) refuse paths over 260 characters. Run
`git config core.longpaths true` in the repository, and keep the repository and the output folder at short paths.

**Can I use it without MacroFab?** The Gerbers, drills (with filled vias split out), PDFs, STEP, ODB++ and the BOM
csvs are generic. The XYRS, the upload zip naming and the xlsx layout are MacroFab's; other assembly houses read
other formats (KiCad's position file, `NAME_pos.csv`, is in the package for reference).
