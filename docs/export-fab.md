# kicad-fab-export

```text
kicad-fab-export REV --out DIR [options]
kicad-fab-export --zip-only --out DIR
```

Exports the fabrication and assembly package of commit `REV` into `DIR`, checks it, and packs the MacroFab upload
zip. With `--pcbway` it also writes PCBWay's BOM, centroid files and Gerber zip ([PCBWay](pcbway.md)). Every flag is
in the [CLI reference](cli.md#kicad-fab-export).

## How a run goes

1. **Project copy.** `git archive REV` of the project folder (and, with [`library_dir`](configuration.md#library_dir),
   of the part library: a submodule at the commit the board points it at, or a folder of the repository such as
   `../lib` from `REV` itself) is unpacked into a temporary work folder. No design file is read from the
   working tree (only the optional [config file](configuration.md#the-config-file) is), and nothing in the repository
   is written. `REV` can be any commit, including one on no branch (that is a warning, see
   [checks](#checks)).
2. **Facts.** The board text (plot settings, layers, vias, the `REVISION` property), a `pcbnew` dump run with
   KiCad's Python (outline, footprints, pads, paste, courtyards, vias), and the schematic netlist and BOM from
   `kicad-cli`.
3. **Steps.** Gerbers, drill, placement (XYRS and position file), paste, schematic PDF, assembly PDF, STEP, ODB++,
   iBOM, and with `--pcbway` the PCBWay BOM and centroid files. A step whose inputs failed is skipped (`SKIP ... needs gerbers`), the others still run.
4. **Checks** are collected throughout (see [Checks](#checks)); then the layer map, the upload zip (and with
   `--pcbway` the PCBWay Gerber zip) and the manifest are written, and a summary is printed.

The outputs are written even when a check fails, so you can look at what is wrong. On success the work folder is
deleted (unless `--work DIR` or `--keep-work`); on failure it is kept and the last summary line names it.

`NAME`, the prefix of every file, is `--name`, else the [`name_template`](configuration.md#name_template)
(`{project}_v{revision}` by default, with the board's `REVISION` property). It must match `[A-Za-z0-9_.-]+`.

## Output files

| File | What it is | Notes |
|---|---|---|
| `fab/NAME_<layer>.gbr` | Gerbers: every copper layer, F/B mask, F/B paste, F/B silkscreen, Edge.Cuts | plotted with `kicad-cli pcb export gerbers --board-plot-params` (the board's own plot settings). The layer part of the name is KiCad's file name without the `<project>-` prefix, every run of other characters made `_` (`L3 (+Sig2)` becomes `NAME_L3_Sig2.gbr`) |
| `fab/NAME_job.gbrjob` | KiCad's Gerber job file | cut to the fab Gerbers and renamed to match them |
| `fab/NAME_layer_map.csv` | KiCad layer, board layer name, function, polarity, fab file, KiCad file, upload file | one row per Gerber and per drill file (example below) |
| `fab/NAME_PTH.drl` | plated holes | Excellon, mm, decimal, absolute origin (the Gerber frame) |
| `fab/NAME_PTH_FILLED.drl` | filled-and-capped vias (IPC-4761 Type VII) | moved out of the PTH file; always written, empty on a board without filled vias |
| `fab/NAME_NPTH.drl` | non-plated holes | |
| `fab/NAME_PTH_drl_map.pdf`, `fab/NAME_NPTH_drl_map.pdf` | KiCad's drill maps | before the split |
| `fab/NAME_drill_report.txt` | KiCad's drill report | with the split and a tool table of the three final files appended |
| `fab/NAME_odb.zip` | ODB++ | reference only, never in the upload zip |
| `assembly/NAME.XYRS` | MacroFab placement file | see [XYRS](xyrs.md) |
| `assembly/NAME_pos.csv` | KiCad's position file | csv, mm, both sides, absolute origin (so Y is negative), raw KiCad rotation, DNP parts left out; reference only |
| `assembly/NAME_assembly.pdf` | assembly drawing: page 1 F.Fab + Edge.Cuts, page 2 B.Fab + Edge.Cuts mirrored | title block, 1:1, black and white, DNP parts sketched and crossed out. Without `pypdf`: two one-page files, `_assembly_top.pdf` and `_assembly_bottom.pdf` (the designator check still runs on them) |
| `assembly/NAME_ibom.html` | InteractiveHtmlBom page, pin 1 highlighted | only with `--ibom-pkg` |
| `docs/NAME_schematic.pdf` | the whole schematic hierarchy | KiCad's built-in default colour theme |
| `docs/NAME.step` | board and 3-D models | DNP parts left out (`--step-with-dnp` keeps them); origin = the XYRS corner, so the board spans 0..W x 0..H mm |
| `docs/NAME_export_manifest.json` | the record of the run | see [The manifest](#the-manifest) |
| `NAME_macrofab_upload.zip` | the upload | see [The upload zip](#the-upload-zip) |
| `assembly/NAME_pcbway_bom.xlsx` | PCBWay BOM, in PCBWay's template layout | only with `--pcbway`; see [PCBWay](pcbway.md#the-bom) |
| `assembly/NAME_pcbway_top.csv`, `assembly/NAME_pcbway_bottom.csv` | PCBWay centroid files, one per side | only with `--pcbway`; see [PCBWay](pcbway.md#the-centroid-files) |
| `NAME_pcbway_gerbers.zip` | the fab Gerbers and drill files, for PCBWay | only with `--pcbway`; see [PCBWay](pcbway.md#the-gerber-zip) |
| `bom/...` | written by [`kicad-macrofab-bom`](bom.md) | read here (the xlsx goes into the zip), never written |

The layer map of the demo:

```text
order,kicad_layer,board_layer_name,function,polarity,fab_file,kicad_file,upload_file
1,F.Cu,top_layer,"Copper,L1,Top",Positive,pic_programmer_v1.0_top_layer.gbr,pic_programmer-top_layer.gbr,pic_programmer_v1_0.GTL
2,B.Cu,bottom_layer,"Copper,L2,Bot",Positive,pic_programmer_v1.0_bottom_layer.gbr,pic_programmer-bottom_layer.gbr,pic_programmer_v1_0.GBL
3,F.Paste,F.Paste,"SolderPaste,Top",Positive,pic_programmer_v1.0_F_Paste.gbr,pic_programmer-F_Paste.gbr,pic_programmer_v1_0.GTP
4,B.Paste,B.Paste,"SolderPaste,Bot",Positive,pic_programmer_v1.0_B_Paste.gbr,pic_programmer-B_Paste.gbr,pic_programmer_v1_0.GBP
5,F.Silkscreen,F.Silkscreen,"Legend,Top",Positive,pic_programmer_v1.0_F_Silkscreen.gbr,pic_programmer-F_Silkscreen.gbr,pic_programmer_v1_0.GTO
6,B.Silkscreen,B.Silkscreen,"Legend,Bot",Positive,pic_programmer_v1.0_B_Silkscreen.gbr,pic_programmer-B_Silkscreen.gbr,pic_programmer_v1_0.GBO
7,F.Mask,F.Mask,"SolderMask,Top",Negative,pic_programmer_v1.0_F_Mask.gbr,pic_programmer-F_Mask.gbr,pic_programmer_v1_0.GTS
8,B.Mask,B.Mask,"SolderMask,Bot",Negative,pic_programmer_v1.0_B_Mask.gbr,pic_programmer-B_Mask.gbr,pic_programmer_v1_0.GBS
9,Edge.Cuts,Edge.Cuts,Profile,Positive,pic_programmer_v1.0_Edge_Cuts.gbr,pic_programmer-Edge_Cuts.gbr,pic_programmer_v1_0.BOR
,drill,,"Plated holes, not filled",,pic_programmer_v1.0_PTH.drl,,pic_programmer_v1_0_PTH.XLN
,drill,,"Plated + Filled/Plugged, Non-Conductive (IPC-4761 VII)",,pic_programmer_v1.0_PTH_FILLED.drl,,pic_programmer_v1_0_PTH_FILLED.XLN
,drill,,Non-plated holes,,pic_programmer_v1.0_NPTH.drl,,pic_programmer_v1_0_NPTH.XLN
```

### Gerbers

The fab Gerbers come from the board's own plot settings, so what you see in KiCad's Plot dialog is what you get.
A second plot with explicit flags (`-l <the fab layers> --no-x2 --no-netlist --no-protel-ext --precision 6`, plus
`--subtract-soldermask` / `--disable-aperture-macros` when the board sets them) must give identical files, dates
aside: that check catches a plot setting nobody wrote down. Gerber X2 attributes and netlist attributes must be off.
If the board turns them on, the export does not fail: it takes the files from the explicit `--no-x2 --no-netlist`
plot instead, prints a warning per setting and says so in a `NOTE` (see the
[unmodified demo](troubleshooting.md#x2-attributes-and-protel-extensions)). Never `--check-zones`: the zone fills
committed in the board are what gets plotted.

Silkscreen strokes thinner than 0.127 mm (MacroFab's 5 mil minimum line) are counted per width in the summary and
the manifest. That is a count for the DFM email, not a check.

### Drills and filled vias

`kicad-cli pcb export drill` writes Excellon in mm with decimal coordinates, absolute origin and separate plated and
non-plated files. Then every via with `(filling yes)` and `(capping yes)` in the board (or inherited from the board's
`(setup ...)` defaults) is moved, by coordinate and drill size, out of the plated file into `NAME_PTH_FILLED.drl`,
because MacroFab marks fill per drill file. The selection is by those board tokens, never by tool size: a via drill
can sit a few micrometres from a pad drill. The demo's filled-via file:

```text
M48
; Filled and capped vias (IPC-4761 Type VII, non-conductive fill, capped): 4 holes split from pic_programmer_v1.0_PTH.drl by export_fab.py
; DRILL file KiCad 10.0.7 date 2026-10-25T06:37:49
; FORMAT={-:-/ absolute / metric / decimal}
...
METRIC
; #@! TA.AperFunction,Plated,PTH,ViaDrill
T1C0.400
%
G90
G05
T1
X122.0Y-134.0
X124.0Y-134.0
X126.0Y-134.0
X128.0Y-134.0
M30
```

The drill report keeps KiCad's tables (before the split) and appends the split and the final files:

```text
Filled-via split (export_fab.py):
    4 holes (vias with (filling yes) (capping yes) in the board, drill 0.400 mm) moved from pic_programmer-PTH.drl to pic_programmer_v1.0_PTH_FILLED.drl
    (IPC-4761 Type VII: non-conductive epoxy fill, capped). pic_programmer_v1.0_PTH.drl keeps 244 plated holes; pic_programmer_v1.0_NPTH.drl has 7.
    The tables above and the drill maps are KiCad's, before the split (248 plated holes).
    Renamed: pic_programmer-PTH.drl -> pic_programmer_v1.0_PTH.drl, pic_programmer-NPTH.drl -> pic_programmer_v1.0_NPTH.drl.

Final drill files (read back from the three files written; tool, finished diameter mm, hits):
    pic_programmer_v1.0_PTH.drl: 244 holes
        T2  0.600  x6
...
    pic_programmer_v1.0_PTH_FILLED.drl: 4 holes
        T1  0.400  x4
    pic_programmer_v1.0_NPTH.drl: 7 holes
        T1  3.500  x1
        T2  4.300  x6
```

A board without filled vias passes the filled-via checks and gets an empty `NAME_PTH_FILLED.drl`, unless you set
[`require_filled_vias`](configuration.md#require_filled_vias); pin the count with `--expect filled=N` either way.

### Placement, PDFs, STEP, ODB++, iBOM

- **XYRS and position file**: see [XYRS](xyrs.md). The manifest also records each row's pad-1 offset and the parts
  whose body (courtyard centre) is more than 0.25 mm from the XYRS point.
- **Assembly PDF**: `kicad-cli pcb export pdf` of F.Fab (page 1) and B.Fab mirrored (page 2), each with Edge.Cuts,
  the board's drawing sheet and `DOC_TYPE` set to `Top Assembly` / `Bottom Assembly`, merged with `pypdf` (two
  files without it). With PyMuPDF, every XYRS designator must be printed on its side's page; that check runs on
  the merged file or on the two files alike.
- **STEP**: `--subst-models --min-distance 0.01mm --user-origin <XYRS corner>`, DNP parts left out. Models resolve as
  in the repository checkout: `${KIPRJMOD}/<library_dir>/...` from the staged library (a submodule, or a folder such
  as `${KIPRJMOD}/../lib/3d_models/...`) and KiCad's own model library (`KICAD10_3DMODEL_DIR`). A footprint that names
  a bare file gets a flat copy only when it has no other model, so no part ends up with two coincident bodies. The
  origin is verified on a second, board-only STEP, whose extent is taken from its edges: their end points and the
  extremes their arcs and circles pass through. A round outline is one STEP circle, written as its centre and one
  seam point, so the end points alone would see half of the board.
- **ODB++**: zip, mm, reference only.
- **iBOM**: run with KiCad's Python from the unpacked InteractiveHtmlBom package given by `--ibom-pkg`, with tracks,
  nets, the `MPN` field and pin 1 highlighted on every part; without `--ibom-pkg` it is skipped with a warning.

## Checks

Each check prints `ok`, `WARN` (printed only) or `FAIL` (exit code 1). A step that raises an error prints `FAIL` in
the steps list and also makes the exit code 1. The names below are the exact check names (with the counts of your
board filled in).

### Board and Gerbers

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `board: unique references on footprints with pads` | error | two footprints share a reference: annotate the board |
| `board plot params: X2 attributes off (usegerberattributes no)` | warn | X2 is on in the Plot dialog; the files come from the explicit X1 plot instead. Turn it off and save the board |
| `board plot params: netlist attributes off (usegerberadvancedattributes no)` | warn | the same for netlist attributes |
| `board plot params: absolute origin (useauxorigin no)` | error | "Use drill/place file origin" is on; the drills, Gerbers and XYRS must share the absolute frame |
| `gerbers: N copper + 7 fab layers in the gbrjob` | error | the board's plot settings do not select every fab layer; the step fails with `fab layer set incomplete` ([example](troubleshooting.md#fab-layer-set-incomplete)) |
| `gerbers: X2 off in all N files (no %TF/%TA/%TO/%TD lines)` | error | an X2 attribute line is in a written file |
| `gerbers: --board-plot-params output identical to the pinned flags (...)` | warn | the board's plot settings differ from the written-down flags (Protel extensions, precision, ...); the detail names each file, including files written by only one of the two plots |
| `outline: Edge.Cuts Gerber extents = pcbnew centre-line box (Y negated)` | error | the outline Gerber and the board disagree by 1 um or more: a broken or open outline, or graphics on Edge.Cuts outside the board |

### Drills

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `drill: Excellon header has METRIC and FMAT,2` | error | an unexpected Excellon header (a kicad-cli change) |
| `drill: no slots / routed holes (MacroFab wants slots on Edge.Cuts)` | error | an oval pad drill or a routed hole; draw the slot on Edge.Cuts instead |
| `drill: every via is a through via F.Cu-B.Cu` | error | a blind, buried or micro via |
| `drill: pcbnew and the board text list the same number of vias` | error | the board text parser and pcbnew disagree (report it as a bug) |
| `drill: pcbnew sees the same filled vias (...)` | error | the vias pcbnew reports as filled and capped are not the set found in the board text; with `require_filled_vias`, also a board with none |
| `drill: protected vias are all filled AND capped (Type VII)` | error | a via is filled but not capped, or capped but not filled |
| `drill: each filled via found exactly once in the PTH file` | error | a filled via has no hit (or more than one) at its coordinate and drill size in KiCad's PTH file; with `require_filled_vias`, also a board with none |
| `drill: map PTH/NPTH written` | error | KiCad wrote no drill map (only shown when it fails) |
| `drill: PTH + filled = KiCad PTH (a + b = c)` | error | holes were lost or duplicated in the split |
| `drill: all N hits inside the outline (...)` | error | a hit outside the board: a wrong drill origin |
| `drill/Gerber line-up on <layer>: every plated hit sits on a copper flash` | error | a plated hit without a pad or via flash on an outer copper layer at that point: a frame mismatch |

### Placement

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `XYRS: every row inside 0..W x 0..H mil (no negatives)` | error | a part's pad box centre is outside the outline box |
| `XYRS: board and schematic agree (DNP, BOM exclusion, value, footprint, MPN; MPN on fitted parts; ASCII)` | error | the detail lists each disagreement (Update PCB from Schematic), each fitted part with no `MPN`, and each non-ASCII value, footprint or MPN |
| `XYRS: Populate 1 set = the kicad-cli BOM refs (N)` | error | the parts the XYRS marks fitted are not the parts in kicad-cli's BOM (usually a DNP part still in the BOM) |
| `XYRS: <ref> rotation r rounded to n`, `XYRS: <ref> has no pads: footprint origin used`, `XYRS: <ref> Populate 1 but Value/MPN ... contains DNP/DNM` | warn | an off-grid rotation (the XYRS has whole degrees), a part placed by its origin, or text MacroFab may read as "do not place" |
| `XYRS: N data rows, 12 tab fields each` | error | a tab or line break inside a field |
| `pos: rows = footprints not excluded from pos files and not DNP (N)` | error | KiCad's position file has other rows than expected |
| `pos: absolute frame = Gerber frame (...)` | error | KiCad's position file is not in the absolute frame |
| `XYRS vs KiCad pos: same frame on the N parts whose origin is the pad centre (...)` | error | the XYRS transform disagrees with KiCad's own file (or no part has its origin at its pad centre to compare) |
| `XYRS vs KiCad pos: rotation = pos Rot (top) / pos Rot + 180 (bottom) on all N shared parts` | error | the rotation rule disagrees with KiCad's file |

### Paste on parts that are not placed

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `paste: no paste in the board on the N Populate 0 parts (...)` | error | a Populate 0 part has pads on a paste layer, or footprint graphics on F/B.Paste (a filled exposed-pad window is the usual one; named by uuid) |
| `paste: no paste flash, region or draw inside a Populate 0 part's pad box (its own side)` | error | the plotted paste Gerber prints paste where nothing will be placed |
| `paste: <ref> carries paste, accepted by --accept-dnp-paste: ...` | warn | you accepted it; tell MacroFab "no paste at `<ref>`" (also written as a `NOTE`) |
| `paste: <ref> is in --accept-dnp-paste but carries no paste: drop it from the list` | warn | a stale entry |
| `paste: every fitted SMT (Type 1) row has paste in its pad box (...)` | warn | a fitted SMT part without paste; also the control that the paste checks see paste at all |
| `paste: no board-level (non-footprint) graphics on F/B.Paste` | warn | board graphics on a paste layer, not tied to any part |

### PDFs, STEP, ODB++, iBOM

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `schematic PDF: N pages >= M hierarchy sheets` | error | sheets missing from the PDF |
| `assembly PDF: pypdf missing, written as two files` | warn | install `pypdf` (`[pdf]` extra); the designator check below still runs, on the two files |
| `assembly PDF: 2 pages (top, bottom mirrored)` | error | the merge went wrong |
| `assembly PDF: designators not checked (no PyMuPDF)` | warn | install PyMuPDF (`[pdf]` extra; AGPL-3.0) to run the next check |
| `assembly PDF: every XYRS designator is printed on its side's page (N)` | error | a placed part has no `${REFERENCE}` text on its Fab layer ([example](troubleshooting.md#designators-missing-on-the-assembly-drawing)) |
| `STEP: components in the file = parts with a resolved model (N)` | warn | the STEP has other components than expected |
| `STEP: parts whose footprint lists the same model file twice (...)` | warn | two coincident bodies |
| `STEP: <library_dir> 3-D models added to the project copy` | error | with `library_dir` set: the library's models could not be staged (no submodule checkout has the commit, or there is no such submodule or folder at `REV`, or nothing in `library_model_paths`) |
| `STEP: every placed part with a model entry gets a model` | error | every model entry of a part points at a file that does not exist |
| `STEP: N model entries do not resolve (each of these parts has another entry that does)` | warn | extra model entries that do not resolve |
| `STEP: fitted parts with no 3-D model in their footprint` | warn | the footprint has no model at all |
| `STEP: origin = XYRS corner (board spans 0..W x 0..H mm)` | error | the board-only STEP's edges (end points, arc and circle extremes) do not span 0..W x 0..H: the STEP origin is not the XYRS corner |
| `ODB++: components = placed footprints (N)` | warn | kicad-cli's ODB++ lists other components |
| `ODB++: filling layer carries the filled vias` | warn | the ODB++ filling layer does not match the filled vias |
| `iBOM: skipped (no --ibom-pkg)` | warn | no iBOM was asked for |
| `iBOM: BOM parts = XYRS Populate 1 (...)` | error | the iBOM and the XYRS disagree on fitted parts or sides |
| `iBOM: title block revision = R` | error | the iBOM page shows another revision |
| `iBOM: pin 1 highlighted on every part (highlight_pin1 = all)` | warn | the InteractiveHtmlBom version ignored the option |

### PCBWay (with `--pcbway`)

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `PCBWay BOM: N lines for the M XYRS rows, each designator once, Qty = its designators, DNS = Populate 0, MPN / Value / Footprint / Type as in the XYRS` | error | the BOM read back from the xlsx does not carry each XYRS designator exactly once, a line's `*Qty` is not its number of designators, or a line's Type, MPN, Value or Footprint is not the XYRS's for one of its designators (a non-ASCII character is compared as the XYRS writes it, `?`) |
| `PCBWay centroid: the Populate 1 XYRS rows, a top / b bottom, at the XYRS point x 0.0254 mm (max diff d mm)` | error | a centroid file has other designators or another order than the side's Populate 1 XYRS rows, a point more than 0.0002 mm from the XYRS point, or the wrong Layer |
| `PCBWay centroid vs KiCad pos: rotation = pos Rot and side = pos Side on all N shared parts (no +180 on the bottom)` | error | a centroid rotation or side is not KiCad's own, as its position file gives it |
| `PCBWay Gerber zip: N members (G Gerbers, PTH + NPTH drills), CRC ok, byte-identical to the fab files, no assembly or reference files` | error | the zip is corrupt, differs from the files in `fab/`, or holds a file that is not a fab Gerber or drill file |

### Counts, commit and zip

| Check | Level | A FAIL / WARN means |
|---|---|---|
| `expect KEY = N` | error | a `--expect` count changed ([example](troubleshooting.md#an-expected-count-changed)) |
| `source commit is on a branch or tag (...)` | warn | `REV` is a scratch commit on no branch or tag; its hash and subject go into the XYRS header, the manifest and the zip dates, so re-run on the final commit before keeping the outputs |
| `upload zip: member names are flat, start with BASE and have exactly one dot (before the extension)` | error | a member name MacroFab could misread |
| `xlsx vs XYRS: same designators (N), unique, same Populate` | error | `bom/NAME_macrofab.xlsx` and the XYRS disagree; the zip is **not** written (an existing zip is reported as out of date). Re-run both tools on the same commit |
| `xlsx vs XYRS: xlsx has a Designator column` | error | the xlsx in `bom/` is not a MacroFab BOM |
| `xlsx vs XYRS: openpyxl missing, not checked` | warn | install openpyxl |
| `upload zip: no bom/NAME_macrofab.xlsx yet (...)` | warn | the zip was packed without the BOM; run `kicad-macrofab-bom`, then `--zip-only` |
| `upload zip: N members, CRC ok, byte-identical to the package files, no PDF / ODB++ / gbrjob` | error | the zip is corrupt or differs from the files it was built from |

`--expect` keys: `fitted` (Populate 1 rows), `rows` (all XYRS rows), `pop0`, `fitted_top`, `fitted_bottom`, `pth`
(plated hits, filled vias excluded), `filled`, `npth`, `pages` (schematic PDF pages).

## The manifest

`docs/NAME_export_manifest.json` records the run. Local paths are written as tags (`<repo>`, `<main-checkout>`,
`<work>`, `<out>`, `<export_fab.py>`, `<ibom-pkg>`, `kicad-cli`, `kicad-python`), so manifests from two machines can be
diffed. Its keys, with values from the demo's v1.1 package (trimmed):

| Key | Contents | Example |
|---|---|---|
| `name`, `upload_base` | NAME and the dot-free upload base | `"pic_programmer_v1.1"`, `"pic_programmer_v1_1"` |
| `board`, `revision`, `release_date` | the board's `BOARD_NAME`, `REVISION` and `RELEASE_DATE` properties | `null`, `"1.1"`, `null` |
| `commit`, `subject`, `commit_date`, `refs_containing_commit` | the source commit | `"b483688d28da..."`, `["refs/heads/main", "refs/tags/v1.1"]` |
| `kicad`, `generator`, `ibom`, `library` | tool versions and the library status | `"KiCad 10.0.7"`, `"export_fab.py"` |
| `xyrs_origin_kicad_mm`, `board_size_mil`, `board_size_mm` | the XYRS frame | `[73.66, 139.7]`, `[6300.0, 3900.0]`, `[160.02, 99.06]` |
| `aux_origin_mm_not_used`, `plot_params`, `forced_x1` | the board's aux origin (ignored), its plot settings, whether X2 forced the X1 plot | `[62.23, 153.67]`, `{...}`, `false` |
| `layer_map` | the layer map rows | |
| `filled_vias`, `fiducials`, `xyrs_omitted`, `board_only_logos` | what was split out or left out | `[{"x_mm": 122.0, "y_mm": 134.0, "drill_mm": 0.4}, ...]` |
| `paste` | the paste findings | `{"populate0_checked": 1, "board_sources": {}, ...}` |
| `xyrs_pad1`, `xyrs_body_offsets` | placement-review data, see [XYRS](xyrs.md#placement-review-data) | |
| `models` | STEP model resolution | `{"entries": 54, "missing_entries": 0, "fitted_parts_without_model": ["P3", "RV1"], ...}` |
| `pcbway` | only with `--pcbway`: the BOM's path and line counts, each centroid file's path and rows, the Gerber zip's path, members, bytes and sha256 | `{"bom": "assembly/pic_programmer_v1.0_pcbway_bom.xlsx", "bom_lines": 37, "dns_lines": 1, ...}` |
| `counts`, `notes`, `steps`, `checks` | what the summary prints | `{"name": ..., "level": "error", "ok": true, "detail": ""}` per check |
| `commands` | every external command, in order | `"kicad-cli pcb export gerbers --board-plot-params -o <work>/gerber_bpp/ <work>/proj/hw/pic_programmer.kicad_pcb"` |
| `upload_zip` | path, members, bytes, sha256 of the zip | |
| `outputs` | path, bytes, sha256 of every file this tool wrote | `{"path": "assembly/pic_programmer_v1.1.XYRS", "bytes": 6478, "sha256": "499f9faf..."}` |
| `other_files` | the same for every other file in DIR (`bom/`, `README.md`, ...) | `{"path": "README.md", "bytes": 123, ...}` |

## The upload zip

`NAME_macrofab_upload.zip` holds exactly what MacroFab reads, flat, under a dot-free base name `BASE` (NAME with
every `.` replaced by `_`), so the only dot in each member name is the one before the extension MacroFab identifies
the layer by:

| Member | Source |
|---|---|
| `BASE.GTL`, `BASE.G2L` ... `BASE.G<n>L` (`G<n>P` for a negative plane), `BASE.GBL` | copper, top to bottom |
| `BASE.GTS`, `BASE.GBS` | solder mask |
| `BASE.GTO`, `BASE.GBO` | silkscreen |
| `BASE.GTP`, `BASE.GBP` | paste |
| `BASE.BOR` | Edge.Cuts |
| `BASE_PTH.XLN`, `BASE_PTH_FILLED.XLN`, `BASE_NPTH.XLN` | the three drill files |
| `BASE.XYRS` | placement |
| `BASE_macrofab.xlsx` | `bom/NAME_macrofab.xlsx`, when it exists (its designators and Populate must equal the XYRS's) |

No PDF, ODB++ or job file goes in. Member dates are the commit date, so the zip of a commit is reproducible (only
the timestamps KiCad writes inside the Gerbers and drill files differ between runs). The demo's v1.1 zip:

```text
pic_programmer_v1_1.GTL                     66571  2026-10-22 09:00:00
pic_programmer_v1_1.GBL                    309036  2026-10-22 09:00:00
pic_programmer_v1_1.GTP                       510  2026-10-22 09:00:00
pic_programmer_v1_1.GBP                       510  2026-10-22 09:00:00
pic_programmer_v1_1.GTO                    115088  2026-10-22 09:00:00
pic_programmer_v1_1.GBO                      1818  2026-10-22 09:00:00
pic_programmer_v1_1.GTS                      9400  2026-10-22 09:00:00
pic_programmer_v1_1.GBS                      9985  2026-10-22 09:00:00
pic_programmer_v1_1.BOR                       809  2026-10-22 09:00:00
pic_programmer_v1_1_PTH.XLN                  5101  2026-10-22 09:00:00
pic_programmer_v1_1_PTH_FILLED.XLN            529  2026-10-22 09:00:00
pic_programmer_v1_1_NPTH.XLN                  522  2026-10-22 09:00:00
pic_programmer_v1_1.XYRS                     6478  2026-10-22 09:00:00
pic_programmer_v1_1_macrofab.xlsx            7750  2026-10-22 09:00:00
```

`kicad-fab-export --zip-only --out DIR` rebuilds the zip from the files in `DIR` (no KiCad, no commit needed: the
names come from the manifest) and refreshes the manifest's zip entry, checks and file hashes. Use it after
`kicad-macrofab-bom` wrote or rewrote `bom/`, or after you added a README.

## Deliberate behaviours

Some behaviours look like shortcuts but are on purpose:

- **Outputs are written even when a check fails.** You see every problem in one run instead of one per run. Exit
  code 1 still tells scripts not to use them.
- **Non-ASCII characters become `?` in the XYRS.** A non-ASCII Value, Footprint or MPN fails the
  `XYRS: board and schematic agree ...` check, and the XYRS is written in ASCII with `?` in its place, so the rest of
  the package (and the other findings) are still produced. Fix the field; never upload that XYRS.
- **The pinned-flag cross-check warns, it does not crash, when one plot wrote a file the other did not** (for
  example Protel extensions on in the board, where one plot writes `.gtl` and the other `.gbr`). The detail names
  each such file as `(not written by both plots)`.
- **X2 or netlist attributes on in the board do not fail the export**: the explicit X1 plot is used, with a warning
  per setting and a `NOTE`.
- **No filled vias is not an error** unless `require_filled_vias` is set; `NAME_PTH_FILLED.drl` is written anyway (with
  no holes), so the upload always has the same three drill files.
- **A Gerber job file is always produced**, even when the board's settings turn the job file off (KiCad 10.0.7 then
  writes one in the explicit plot, which is used).
- **The outline corner is rounded to 0.1 um** before the XYRS frame is set, because pcbnew's bounding boxes can be
  1 nm off the outline, enough to flip the last printed digit of a coordinate.
- **Rotations are rounded to whole degrees** in the XYRS, with a warning for any part not on a whole degree.
- **The drill report and drill maps are KiCad's, from before the split**; the split and the final tool tables are
  appended to the report rather than editing KiCad's tables.
- **A scratch commit is a warning, not an error**, so you can try changes on a detached commit; the warning tells you
  not to keep those outputs.
- **Board-only footprints with no pads** (logos) and parts excluded from the board get no XYRS row and are listed in
  the header.
- **`--accept-dnp-paste REFS`** downgrades paste on those Populate 0 parts to a warning plus a `NOTE` for the order,
  for the case where the board cannot change before the order.
- **A failed export keeps its work folder**; delete it yourself after looking.

## Reproducibility

Re-running a commit reproduces the XYRS, the position file, the layer map, the BOM xlsx and csvs, the PCBWay BOM
and centroid files and the reports byte for byte. Gerbers, drill files, the Gerber job, the drill report and the PDFs
differ only in the timestamps KiCad writes into them (and so does the content of the upload zip and the PCBWay Gerber
zip). KiCad's STEP and ODB++ writers also renumber entities and
reorder features between runs, so compare those structurally. The xlsx is reproducible for a given openpyxl version,
with or without lxml installed (see [the xlsx](bom.md#the-xlsx) for `OPENPYXL_LXML`).
