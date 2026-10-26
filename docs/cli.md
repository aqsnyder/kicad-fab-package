# CLI reference

Five console scripts are installed with the package. Each also runs as a module, `python -m
kicad_fab_package.<module>`, and `python -m kicad_fab_package COMMAND ARGS...` runs one by name:

| Command | Module | Page |
|---|---|---|
| `kicad-fab-export` | `export_fab` | [export-fab.md](export-fab.md) |
| `kicad-macrofab-bom` | `make_macrofab_xlsx` | [bom.md](bom.md#kicad-macrofab-bom) |
| `kicad-bom-check` | `bom_check` | [bom.md](bom.md#kicad-bom-check) |
| `kicad-bomdiff` | `bomdiff` | [bom.md](bom.md#kicad-bomdiff) |
| `kicad-project-copy` | `kproject` | [getting-started.md](getting-started.md#inspecting-a-copy-of-the-project) |

The tables below are generated from the commands' argparse parsers (version 0.1.0); `--help` prints the same flags
with a longer description. In the tables, *Environment* is the variable that sets the value when the flag is not
given, and *Config key* the [config file](configuration.md) key; precedence is **flag > environment > config file >
default**. A boolean key has a `--x` flag that sets it and a `--no-x` flag that clears it, whatever the config file
says.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | ok; warnings may have been printed. `kicad-bomdiff` exits 0 whenever it could compare the two files, whatever differences it found |
| `1` | a check or a step failed (the outputs are still written); for `kicad-bom-check`, the csvs differ |
| `2` | setup error: bad arguments, no git repository, kicad-cli or KiCad's python not found, unreadable config, a non-empty output folder without `--force`, an input file that is missing or unreadable (for `kicad-bomdiff` also a csv with no `Reference` column, or a grouped BOM), ... |

A setup error prints one `ERROR: ...` line that says what is wrong:

```text
$ kicad-bomdiff nope_a.csv nope_b.csv
ERROR: nope_a.csv: file not found
$ kicad-bomdiff ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv ../bomdiff/v1.1/v1.1.perref.csv
ERROR: ../fab/v1.1/bom/pic_programmer_v1.1_bom.csv: a grouped BOM (Reference 'C6,C7'); kicad-bomdiff reads per-reference csvs, as `kicad-bom-check REV --perref --out DIR` writes them
```

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `KICAD_CLI` | export, BOM, bom-check | the `kicad-cli` executable; when set, nothing is auto-detected |
| `KICAD_PYTHON`, `KICAD10_PYTHON` | export | KiCad's Python (the one that can `import pcbnew`), first one set wins |
| `KICAD10_3DMODEL_DIR` | export | KiCad's 3-D model library, passed to kicad-cli as `KICAD9_3DMODEL_DIR` and `KICAD10_3DMODEL_DIR` |
| `KICAD_FAB_CONFIG` | all but `kicad-bomdiff` | the config file, when `--config` is not given |
| `OPENPYXL_LXML` | BOM | openpyxl's own switch. `kicad-macrofab-bom` sets it to `False` when it is not set, so the xlsx has the same bytes with or without lxml installed; `True` lets openpyxl write through lxml (same cells, different bytes). See [the xlsx](bom.md#the-xlsx) |

Auto-detection, when neither the flag nor the variable is set:

- **kicad-cli**: the newest standard install first (`<Program Files>/KiCad/<version>/bin/kicad-cli.exe`, newest
  version first, including the per-user `%LOCALAPPDATA%/Programs/KiCad` on Windows;
  `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` on macOS; `/usr/bin/kicad-cli`, `/usr/local/bin/kicad-cli`
  on Linux), then `kicad-cli` on `PATH`. The standard install comes first because `PATH` often still points at an
  older KiCad. Whatever is found, a `kicad-cli` older than KiCad 10 gets a warning on stderr:

  ```text
  WARNING: <KiCad 9.0>/bin/kicad-cli.exe is KiCad 9.0.8; these tools are written for KiCad 10 (board format, kicad-cli options). Point --kicad-cli or KICAD_CLI at a KiCad 10 kicad-cli.
  ```

- **KiCad's Python**: next to `kicad-cli` (`python.exe` in the same `bin` folder on Windows, the app bundle's
  `Python.framework` on macOS, `python3` beside it on Linux), then the standard install folders, then
  `/usr/bin/python3` on Linux.
- **3-D models**: `share/kicad/3dmodels` next to `kicad-cli` (`SharedSupport/3dmodels` on macOS), then the standard
  install folders. When none is found, KiCad's own default applies.

## `kicad-fab-export`

```
usage: kicad-fab-export [-h] --out DIR [--repo DIR] [--no-zip] [--zip-only]
                        [--name NAME] [--work DIR] [--keep-work]
                        [--expect KEY=N,...] [--step-with-dnp] [--force]
                        [--accept-dnp-paste REFS] [--config FILE]
                        [--project-dir DIR] [--name-template TEMPLATE]
                        [--library-dir DIR] [--library-paths P1,P2]
                        [--library-model-paths P1,P2]
                        [--generator-prefix PREFIX] [--require-dru]
                        [--no-require-dru] [--kicad-cli PATH]
                        [--kicad-python PATH] [--kicad-3dmodel-dir DIR]
                        [--ibom-pkg DIR] [--non-part-refs REGEX]
                        [--non-part-libs L1,L2] [--xyrs-non-part-refs REGEX]
                        [--xyrs-non-part-libs L1,L2] [--require-filled-vias]
                        [--no-require-filled-vias] [--pcbway] [--no-pcbway]
                        [REV]
```

| Argument | Default | Environment | Config key | Description |
|---|---|---|---|---|
| `REV` | none |  |  | the commit to export: any commit-ish (HEAD, a branch, a tag, a hash); required except with --zip-only |
| `--out DIR` | (required) |  |  | the package folder (created if needed); fab/, assembly/ and docs/ must be empty unless --force |
| `--repo DIR` | `.` |  |  | the git repository (default: the current folder) |
| `--no-zip` | off |  |  | do not write the upload zip (nor, with --pcbway, the PCBWay Gerber zip) |
| `--zip-only` | off |  |  | only re-pack the upload zip from the files already in --out and refresh the manifest (no REV, no KiCad) |
| `--name NAME` | none |  |  | output name prefix (default: the name template) |
| `--work DIR` | none |  |  | work folder, kept (an empty or new folder); default: a temp folder removed on success |
| `--keep-work` | off |  |  | keep the temp work folder on success too |
| `--expect KEY=N,...` | none |  |  | fail unless these counts hold; KEY in fitted, rows, pop0, fitted_top, fitted_bottom, pth, filled, npth, pages |
| `--step-with-dnp` | off |  |  | keep DNP parts in the STEP |
| `--force` | off |  |  | write into non-empty fab/ assembly/ docs/ (same names are overwritten, other files are left and listed) |
| `--accept-dnp-paste REFS` | none |  |  | comma list of Populate 0 parts whose paste is accepted (a warning and a note instead of an error); only when the board cannot change and MacroFab is told "no paste at REFS" |
| `--config FILE` | see [Configuration](configuration.md#the-config-file) | `KICAD_FAB_CONFIG` |  | config file (default: $KICAD_FAB_CONFIG, else kicad-fab.toml or kicad-fab.json at the repo top level) |
| `--project-dir DIR` | auto-detected |  | `project_dir` | project folder inside the repo, "." for the top level (default: auto-detected, the folder of the only .kicad_pro with a .kicad_pcb of the same name) |
| `--name-template TEMPLATE` | `{project}_v{revision}` |  | `name_template` | NAME when --name is not given: {project} = KiCad project name, {revision} = its REVISION (default '{project}_v{revision}') |
| `--library-dir DIR` | none |  | `library_dir` | library folder relative to the project folder: a git submodule or a plain folder of the repository (e.g. ../lib); its files are added to the project copy ("" = none; default: none) |
| `--library-paths P1,P2` | `[]` |  | `library_paths` | folders of the library put into the project copy (default: the whole library) |
| `--library-model-paths P1,P2` | `[]` |  | `library_model_paths` | folders of the library holding 3-D models (default: the whole library) |
| `--generator-prefix PREFIX` | `""` |  | `generator_prefix` | prefix of the tool name written into the outputs (default '') |
| `--require-dru`, `--no-require-dru` | `false` |  | `require_dru` | require &lt;project&gt;.kicad_dru in the project copy; `--no-require-dru`: do not require &lt;project&gt;.kicad_dru, whatever the config file says |
| `--kicad-cli PATH` | auto-detected | `KICAD_CLI` | `kicad_cli` | kicad-cli (env KICAD_CLI; default: the newest standard install, then PATH; a kicad-cli older than KiCad 10 gets a warning) |
| `--kicad-python PATH` | auto-detected | `KICAD_PYTHON`, `KICAD10_PYTHON` | `kicad_python` | KiCad's python with pcbnew (env KICAD_PYTHON or KICAD10_PYTHON; default: next to kicad-cli, then the standard install folders) |
| `--kicad-3dmodel-dir DIR` | auto-detected | `KICAD10_3DMODEL_DIR` | `kicad_3dmodel_dir` | KiCad's 3-D model library (env KICAD10_3DMODEL_DIR; default: auto-detected next to kicad-cli) |
| `--ibom-pkg DIR` | none (no iBOM) |  | `ibom_pkg` | unpacked InteractiveHtmlBom package folder (run with KiCad's python); without it the iBOM is skipped |
| `--non-part-refs REGEX` | `^(FID\|H)\d+$` |  | `non_part_refs` | designators of fiducials and mounting holes, matched from the start (default ^(FID\|H)\d+$; "" = none) |
| `--non-part-libs L1,L2` | `["Fiducial", "MountingHole"]` |  | `non_part_libs` | footprint libraries of fiducials and mounting holes (default Fiducial,MountingHole; "" = none) |
| `--xyrs-non-part-refs REGEX` | same as `non_part_refs` |  | `xyrs_non_part_refs` | --non-part-refs for the XYRS only (default: --non-part-refs) |
| `--xyrs-non-part-libs L1,L2` | same as `non_part_libs` |  | `xyrs_non_part_libs` | --non-part-libs for the XYRS only (default: --non-part-libs) |
| `--require-filled-vias`, `--no-require-filled-vias` | `false` |  | `require_filled_vias` | fail the filled-via checks when the board has no filled-and-capped vias; `--no-require-filled-vias`: a board without filled-and-capped vias passes the filled-via checks, whatever the config file says |
| `--pcbway`, `--no-pcbway` | `false` |  | `pcbway` | also write the PCBWay assembly files: BOM xlsx, top and bottom centroid csvs, and the PCBWay Gerber zip; `--no-pcbway`: do not write the PCBWay files, whatever the config file says |

## `kicad-macrofab-bom`

```
usage: kicad-macrofab-bom [-h] --out DIR [--repo DIR] [--name NAME]
                          [--baseline SPEC | --no-baseline]
                          [--expect-fitted N] [--expect-unfitted REFS]
                          [--work DIR] [--config FILE] [--project-dir DIR]
                          [--name-template TEMPLATE] [--baseline-label LABEL]
                          [--revision-label TEMPLATE] [--non-part-refs REGEX]
                          [--non-part-libs L1,L2] [--generator-prefix PREFIX]
                          [--require-dru] [--no-require-dru]
                          [--kicad-cli PATH]
                          [REV]
```

| Argument | Default | Environment | Config key | Description |
|---|---|---|---|---|
| `REV` | `HEAD` |  |  | the commit (default: HEAD) |
| `--out DIR` | (required) |  |  | output folder, created if needed (the package's bom/ folder) |
| `--repo DIR` | `.` |  |  | the git repository (default: the current folder) |
| `--name NAME` | none |  |  | output name prefix (default: the name template) |
| `--baseline SPEC` | none |  |  | BOM xlsx to diff against: REV:PATH (read with git show) or a local file (default: the config file's baseline_paths) |
| `--no-baseline` | off |  |  | skip the diff against a baseline |
| `--expect-fitted N` | none |  |  | fail unless exactly N rows have Populate 1 |
| `--expect-unfitted REFS` | none |  |  | fail unless the Populate 0 designators are exactly REFS (comma list; ranges like TP1-TP8) |
| `--work DIR` | none |  |  | keep the project copy and the intermediate exports there (an empty or new folder); default: a temp folder, removed |
| `--config FILE` | see [Configuration](configuration.md#the-config-file) | `KICAD_FAB_CONFIG` |  | config file (default: $KICAD_FAB_CONFIG, else kicad-fab.toml or kicad-fab.json at the repo top level) |
| `--project-dir DIR` | auto-detected |  | `project_dir` | project folder inside the repo, "." for the top level (default: auto-detected, the folder of the only .kicad_pro with a .kicad_pcb of the same name) |
| `--name-template TEMPLATE` | `{project}_v{revision}` |  | `name_template` | NAME when --name is not given: {project} = KiCad project name, {revision} = its REVISION (default '{project}_v{revision}') |
| `--baseline-label LABEL` | `baseline` |  | `baseline_label` | label of the baseline BOM in the report text and the diff file name (default 'baseline') |
| `--revision-label TEMPLATE` | `v{revision}` |  | `revision_label` | how the diff report calls the new build: {project}, {revision} (default 'v{revision}'; NAME without a revision) |
| `--non-part-refs REGEX` | `^(FID\|H)\d+$` |  | `non_part_refs` | designators of fiducials and mounting holes, matched from the start (default ^(FID\|H)\d+$; "" = none) |
| `--non-part-libs L1,L2` | `["Fiducial", "MountingHole"]` |  | `non_part_libs` | footprint libraries of fiducials and mounting holes (default Fiducial,MountingHole; "" = none) |
| `--generator-prefix PREFIX` | `""` |  | `generator_prefix` | prefix of the tool name written into the outputs (default '') |
| `--require-dru`, `--no-require-dru` | `false` |  | `require_dru` | require &lt;project&gt;.kicad_dru in the project copy; `--no-require-dru`: do not require &lt;project&gt;.kicad_dru, whatever the config file says |
| `--kicad-cli PATH` | auto-detected | `KICAD_CLI` | `kicad_cli` | kicad-cli (env KICAD_CLI; default: the newest standard install, then PATH; a kicad-cli older than KiCad 10 gets a warning) |

## `kicad-bom-check`

```
usage: kicad-bom-check [-h] [--repo DIR] [--csv PATH | --against FILE]
                       [--out DIR] [--perref] [--config FILE]
                       [--project-dir DIR] [--require-dru] [--no-require-dru]
                       [--kicad-cli PATH]
                       [REV]
```

| Argument | Default | Environment | Config key | Description |
|---|---|---|---|---|
| `REV` | `HEAD` |  |  | the commit (default: HEAD) |
| `--repo DIR` | `.` |  |  | the git repository (default: the current folder) |
| `--csv PATH` | none |  | `bom_csv` | the committed grouped BOM csv, repo-relative, read at REV (config key bom_csv) |
| `--against FILE` | none |  |  | compare with this local csv instead of a committed one |
| `--out DIR` | none |  |  | keep the regenerated csv(s) here as &lt;rev&gt;.grouped.csv (and &lt;rev&gt;.perref.csv) |
| `--perref` | off |  |  | also export one line per reference (input of kicad-bomdiff) |
| `--config FILE` | see [Configuration](configuration.md#the-config-file) | `KICAD_FAB_CONFIG` |  | config file (default: $KICAD_FAB_CONFIG, else kicad-fab.toml or kicad-fab.json at the repo top level) |
| `--project-dir DIR` | auto-detected |  | `project_dir` | project folder inside the repo, "." for the top level (default: auto-detected, the folder of the only .kicad_pro with a .kicad_pcb of the same name) |
| `--require-dru`, `--no-require-dru` | `false` |  | `require_dru` | require &lt;project&gt;.kicad_dru in the project copy; `--no-require-dru`: do not require &lt;project&gt;.kicad_dru, whatever the config file says |
| `--kicad-cli PATH` | auto-detected | `KICAD_CLI` | `kicad_cli` | kicad-cli (env KICAD_CLI; default: the newest standard install, then PATH; a kicad-cli older than KiCad 10 gets a warning) |

## `kicad-bomdiff`

```
usage: kicad-bomdiff [-h] A.perref.csv B.perref.csv
```

| Argument | Default | Environment | Config key | Description |
|---|---|---|---|---|
| `A.perref.csv` | (required) |  |  | the older per-reference BOM csv |
| `B.perref.csv` | (required) |  |  | the newer per-reference BOM csv |

## `kicad-project-copy`

```
usage: kicad-project-copy [-h] (--rev REV | --worktree) [--repo DIR]
                          [--library {auto,yes,no}] [--full] [--config FILE]
                          [--project-dir DIR] [--library-dir DIR]
                          [--library-paths P1,P2] [--require-dru]
                          [--no-require-dru]
                          DEST
```

| Argument | Default | Environment | Config key | Description |
|---|---|---|---|---|
| `DEST` | (required) |  |  | empty or new folder; the project lands in DEST/&lt;project-dir&gt;/ |
| `--rev REV` | none |  |  | take the files from this commit with git archive |
| `--worktree` | off |  |  | copy the files from the working tree instead |
| `--repo DIR` | `.` |  |  | the git repository (default: the current folder) |
| `--library {auto,yes,no}` | `auto` |  |  | add the library (--library-dir): auto (a submodule if its checkout has the commit, a folder if the commit has it), yes (required) or no (default: auto) |
| `--full` | off |  |  | copy every tracked file of the project folder, not only what KiCad reads |
| `--config FILE` | see [Configuration](configuration.md#the-config-file) | `KICAD_FAB_CONFIG` |  | config file (default: $KICAD_FAB_CONFIG, else kicad-fab.toml or kicad-fab.json at the repo top level) |
| `--project-dir DIR` | auto-detected |  | `project_dir` | project folder inside the repo, "." for the top level (default: auto-detected, the folder of the only .kicad_pro with a .kicad_pcb of the same name) |
| `--library-dir DIR` | none |  | `library_dir` | library folder relative to the project folder: a git submodule or a plain folder of the repository (e.g. ../lib); its files are added to the project copy ("" = none; default: none) |
| `--library-paths P1,P2` | `[]` |  | `library_paths` | folders of the library put into the project copy (default: the whole library) |
| `--require-dru`, `--no-require-dru` | `false` |  | `require_dru` | require &lt;project&gt;.kicad_dru in the project copy; `--no-require-dru`: do not require &lt;project&gt;.kicad_dru, whatever the config file says |

## `python -m kicad_fab_package`

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

`COMMAND` is a command or a module name (`python -m kicad_fab_package export_fab --help`). An unknown command
prints the list and exits 2.
