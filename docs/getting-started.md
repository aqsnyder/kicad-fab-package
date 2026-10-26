# Getting started

This page takes a KiCad 10 project that is committed in git to a checked MacroFab package. The outputs shown are
real (see [the examples](index.md#the-examples-in-these-pages)).

## 1. Install

```bash
pip install git+https://github.com/aqsnyder/kicad-fab-package
```

or from a checkout, with the optional extras:

```bash
git clone https://github.com/aqsnyder/kicad-fab-package
cd kicad-fab-package
pip install ".[pdf,toml]"
```

`[pdf]` adds `pypdf` (one two-page assembly PDF instead of two one-page files) and `PyMuPDF` (checks that every
designator is printed on the assembly drawing, on the merged file or on the two files). Each is used when it is
installed, with or without the other; a missing one is a warning in the summary, never a silent skip. PyMuPDF is
AGPL-3.0 licensed; it is optional, so leave out `[pdf]` (or install only `pypdf`) if that license does not suit you.
`[toml]` adds `tomli`, needed only for a `kicad-fab.toml` config file on Python 3.9 and 3.10. `[all]` installs both
`[pdf]` and `[toml]`.

Check the install:

```text
$ python -m kicad_fab_package
kicad-fab-package 0.1.0

usage: python -m kicad_fab_package COMMAND [ARGS...]

commands:
  kicad-fab-export     (module export_fab)
  kicad-macrofab-bom   (module make_macrofab_xlsx)
  kicad-bom-check      (module bom_check)
  kicad-bomdiff        (module bomdiff)
  kicad-project-copy   (module kproject)
```

KiCad itself is found automatically: `kicad-cli` in the newest standard install (`Program Files/KiCad/<version>/bin`
on Windows, `/Applications/KiCad/KiCad.app` on macOS, `/usr/bin` or `/usr/local/bin` on Linux), else on `PATH`; and
KiCad's Python next to it. Point `--kicad-cli` / `KICAD_CLI` and `--kicad-python` / `KICAD_PYTHON` elsewhere when you
need to. A `kicad-cli` older than KiCad 10 is used but gets a warning on stderr.

## 2. Get the project ready

The tools read the project from a commit, so everything below has to be **committed** before you run them.

| What | Why | How |
|---|---|---|
| One `.kicad_pro` with a `.kicad_pcb` of the same name | the project folder is auto-detected from it | otherwise set `project_dir` (or `--project-dir`) |
| A `REVISION` text variable | output names default to `<project>_v<REVISION>`, e.g. `pic_programmer_v1.0` | define it on the project's Text Variables page (Schematic Setup or Board Setup) and save the board, so the `.kicad_pcb` carries it too; or pass `--name`, or set `name_template` |
| An `MPN` field on every fitted part, and `Manufacturer` | the BOM and the XYRS take the MPN from that field, never from the library id; a fitted part without one fails a check | add the fields to the symbols, then **Update PCB from Schematic** so the footprints carry the same values (the checks compare them) |
| DNP parts marked **Do not populate** and **Exclude from bill of materials** | a DNP part still in the BOM stops `kicad-macrofab-bom`; see [troubleshooting](troubleshooting.md#dnp-but-still-in-the-bom) | both flags on the symbol, then Update PCB |
| Plot settings: F/B copper (and inner layers), F/B mask, F/B paste, F/B silkscreen and Edge.Cuts selected; X2 and netlist attributes off; no Protel extensions; absolute origin | the Gerbers are plotted with the board's own settings, and checked | KiCad's Plot dialog, then save the board |
| Fab-layer designators (`${REFERENCE}` text on F.Fab / B.Fab) | the assembly drawing must show every placed part | the KiCad standard footprints have them |

The checks tell you about anything you missed; [Troubleshooting](troubleshooting.md) shows the messages from running
the tools on KiCad's demo as shipped.

## 3. Build the BOM

`kicad-macrofab-bom` runs first because the upload zip includes its xlsx. Run it from the repository (or pass
`--repo`):

```text
$ cd ~/boards/pic_programmer
$ kicad-macrofab-bom v1.0 --out ../fab/v1.0/bom
rev v1.0 = 8d621b050 (pic_programmer 1.0), kicad-cli 10.0.7, NAME pic_programmer_v1.0
commit on: refs/heads/main, refs/tags/v1.0
rows 57: Populate 1 = 55 (F 55 / B 0), Populate 0 = 2: JP1, R21
no row: P101-P106; board-only footprints: 0
flags: odd MPNs -; MF- house parts 1 MPNs; DNP text on fitted rows -; manufacturer variants [['Demo Parts', 'Demo Parts Inc.']]; value+footprint collisions 0; mixed-Populate groups 1; whitespace stripped 0
wrote: pic_programmer_v1.0_macrofab.xlsx, pic_programmer_v1.0_bom.csv, pic_programmer_v1.0_bom_perref.csv, pic_programmer_v1.0_bom_checks.md -> ../fab/v1.0/bom
CHECKS PASSED
```

`P101`-`P106` are mounting holes (footprints from KiCad's `MountingHole` library, excluded from the BOM, no MPN): they
get no row, in the BOM or in the XYRS. `JP1` is a solder jumper excluded from the BOM and `R21` is DNP: both are
`Populate 0` rows. The flags are reported, not changed: read `pic_programmer_v1.0_bom_checks.md`
([BOM tools](bom.md) explains each one).

## 4. Export the package

```text
$ kicad-fab-export v1.0 --out ../fab/v1.0
-- project copy
-- board facts
...
-- iBOM

== pic_programmer_v1.0 from 8d621b050 (pic_programmer 1.0) -> ~/boards/fab/v1.0

steps:
  ok   project copy           git archive 8d621b050912f40feb09e197dbcd32a008347953; 2 sheets; library: none configured; no library 3-D models (no library folder configured)
  ok   board facts            NAME pic_programmer_v1.0, REVISION 1.0, RELEASE_DATE None, 2 copper layers, 10 vias (4 filled+capped)
  ok   pcbnew facts           edge centre line x 73.6600..233.6800 y 40.6400..139.7000 mm (6300.00 x 3900.00 mil); 63 footprints, 10 vias
  ok   schematic facts        63 schematic symbols (netlist), 55 refs in the kicad-cli BOM
  ok   gerbers                9 Gerbers from --board-plot-params; gbrjob cut to them
  ok   drill                  PTH 244 + FILLED 4 (from 248), NPTH 7; top_layer: 248/248 plated hits on a flash; bottom_layer: 248/248 plated hits on a flash
  ok   placement (XYRS, pos)  XYRS 57 rows (55 Populate 1: 55 top / 0 bottom; 2 Populate 0); omitted P101 P102 P103 P104 P105 P106; pos.csv 62 rows
  ok   paste on unplaced parts F.Paste {'flashes': 0, 'regions': 0, 'draws': 0}, B.Paste {'flashes': 0, 'regions': 0, 'draws': 0}; 2 Populate 0 parts: no paste
  ok   schematic PDF          2 pages
  ok   assembly PDF           2 pages, all 57 designators found
  ok   STEP                   3.5 MB; 53 model entries, 0 unresolved (-); fitted parts without a model: P3 RV1; origin 73.66x139.7mm
  ok   ODB++                  105 members, 63 components, filling layer 4 pads
  ok   iBOM                   skipped
  ok   upload zip             14 members

files:
...
counts:
...
checks:
  ok   board: unique references on footprints with pads
  ok   board plot params: X2 attributes off (usegerberattributes no)  -- usegerberattributes=no
...
  WARN STEP: fitted parts with no 3-D model in their footprint  -- P3 RV1
...
  WARN iBOM: skipped (no --ibom-pkg)
...
NOTE: Silk strokes under 0.127 mm (MacroFab 5 mil minimum; known item for the DFM email): F.Silkscreen 386 x 0.120 mm; B.Silkscreen 4 x 0.120 mm
...
RESULT: ok (2 warnings)
```

It took about ten seconds. Every check line is listed in [kicad-fab-export](export-fab.md#checks); the two warnings
here are expected (two demo footprints have no 3-D model, and no InteractiveHtmlBom package was given). The `NOTE`
lines are facts for the order, not problems: this one belongs in the [DFM email](macrofab.md#the-dfm-email).

## 5. What lands where

```text
~/boards/fab/v1.0/
  pic_programmer_v1.0_macrofab_upload.zip      <- the upload: Gerbers, drills, XYRS, BOM xlsx (flat)
  fab/
    pic_programmer_v1.0_top_layer.gbr            copper (KiCad layer names, prefix dropped)
    pic_programmer_v1.0_bottom_layer.gbr
    pic_programmer_v1.0_F_Mask.gbr  ..._B_Mask.gbr
    pic_programmer_v1.0_F_Paste.gbr ..._B_Paste.gbr
    pic_programmer_v1.0_F_Silkscreen.gbr ..._B_Silkscreen.gbr
    pic_programmer_v1.0_Edge_Cuts.gbr
    pic_programmer_v1.0_job.gbrjob               KiCad's Gerber job file, cut to the files above
    pic_programmer_v1.0_layer_map.csv            KiCad layer -> fab file -> upload file
    pic_programmer_v1.0_PTH.drl                  plated holes
    pic_programmer_v1.0_PTH_FILLED.drl           filled-and-capped vias, split out of the PTH file
    pic_programmer_v1.0_NPTH.drl                 non-plated holes
    pic_programmer_v1.0_PTH_drl_map.pdf  ..._NPTH_drl_map.pdf
    pic_programmer_v1.0_drill_report.txt
    pic_programmer_v1.0_odb.zip                  ODB++ (reference only)
  assembly/
    pic_programmer_v1.0.XYRS                     MacroFab placement file
    pic_programmer_v1.0_pos.csv                  KiCad's position file (reference only)
    pic_programmer_v1.0_assembly.pdf             page 1 top (F.Fab), page 2 bottom (B.Fab, mirrored)
  docs/
    pic_programmer_v1.0_schematic.pdf
    pic_programmer_v1.0.step                     board + models, origin = the XYRS corner
    pic_programmer_v1.0_export_manifest.json     commands, counts, checks, sha256 of every file
  bom/                                           written by kicad-macrofab-bom
    pic_programmer_v1.0_macrofab.xlsx
    pic_programmer_v1.0_bom.csv
    pic_programmer_v1.0_bom_perref.csv
    pic_programmer_v1.0_bom_checks.md
```

With `--ibom-pkg` there is also `assembly/pic_programmer_v1.0_ibom.html`; with a baseline BOM there is also
`bom/pic_programmer_v1.0_vs_<label>.md`; with `--pcbway` there are also the [PCBWay](pcbway.md) files
`assembly/pic_programmer_v1.0_pcbway_bom.xlsx`, `assembly/pic_programmer_v1.0_pcbway_top.csv`,
`assembly/pic_programmer_v1.0_pcbway_bottom.csv` and `pic_programmer_v1.0_pcbway_gerbers.zip`. [kicad-fab-export](export-fab.md#output-files) describes every file.

## 6. After the export

- **Add notes for the order** as a `README.md` in the package folder, edit nothing else by hand, then re-pack:

  ```text
  $ kicad-fab-export --zip-only --out ../fab/v1.1
  ok    upload zip: member names are flat, start with pic_programmer_v1_1 and have exactly one dot (before the extension)
  ok    xlsx vs XYRS: same designators (57), unique, same Populate
  ok    upload zip: 14 members, CRC ok, byte-identical to the package files, no PDF / ODB++ / gbrjob
  wrote ~/boards/fab/v1.1/pic_programmer_v1.1_macrofab_upload.zip (14 members, 123020 bytes)
  ```

  `--zip-only` needs no KiCad and no commit: it rebuilds the zip from the files in the folder and refreshes the
  manifest's file hashes (the README is listed under `other_files`).
- **Pin the counts** of a release you have reviewed, so a later re-export cannot silently change them:

  ```text
  $ kicad-fab-export v1.1 --out ../fab/v1.1 --expect fitted=56,rows=57,pop0=1,fitted_top=56,fitted_bottom=0,pth=244,filled=4,npth=7,pages=2
  ...
    ok   expect fitted = 56  -- got 56
    ok   expect rows = 57  -- got 57
  ...
    ok   expect pages = 2  -- got 2
  ...
  RESULT: ok (2 warnings)
  ```

- **Re-running into the same folder** is refused unless you pass `--force`:

  ```text
  $ kicad-fab-export v1.1 --out ../fab/v1.1
  ERROR: ~/boards/fab/v1.1/fab is not empty (use --force to overwrite same-named files)
  ```

- **Keep the settings with the repository** in a `kicad-fab.toml` at its top level, so nobody has to remember the
  flags. The demo repository has:

  ```toml
  # kicad-fab-package settings for this repository
  project_dir = "hw"
  baseline_paths = ["release/pic_programmer_v1.0_macrofab.xlsx"]
  baseline_label = "v1.0"
  ```

  See [Configuration](configuration.md).
- **Upload to MacroFab**: [the walkthrough](macrofab.md).

## Inspecting a copy of the project

`kicad-project-copy` writes the same checked project copy the tools work on, if you want to open a commit in KiCad
without touching your checkout:

```text
$ kicad-project-copy ../copy --rev v1.1
git archive b483688d28daebc07c24cb37568099d18ee140c1: 6 files, 2 .kicad_sch (2 in the hierarchy of pic_programmer.kicad_sch, all present)
library: none configured
board: ../copy/hw/pic_programmer.kicad_pcb
```
