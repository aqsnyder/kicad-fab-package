# Configuration

Every setting has a generic built-in default, so a repository with one KiCad project at a standard KiCad install
needs no configuration at all. When it does, a setting can come from four places; the first one that gives a value
wins:

1. the command-line flag;
2. an environment variable (only the three KiCad paths have one: `KICAD_CLI`, `KICAD_PYTHON` / `KICAD10_PYTHON`,
   `KICAD10_3DMODEL_DIR`);
3. the config file;
4. the built-in default (for the KiCad paths: [auto-detection](cli.md#environment-variables)).

## The config file

The file is `--config FILE`, else the file named by `$KICAD_FAB_CONFIG`, else `kicad-fab.toml` or `kicad-fab.json` at
the top level of the git repository the tool works on (`--repo`, default the current folder). It is read from the
working tree, not from the commit, so one file serves every commit you export.

- Keys are **flat** (no tables or sections).
- An **unknown key is an error**, so a typo does not pass silently. A wrong type is an error too.
- `null` (JSON) means "use the default".
- Relative paths in the four machine-path keys (`kicad_cli`, `kicad_python`, `kicad_3dmodel_dir`, `ibom_pkg`) are
  resolved against the config file's folder; `~` is expanded.
- TOML needs Python 3.11 or newer, or the `tomli` package (`pip install "kicad-fab-package[toml]"`). JSON always
  works.

The demo repository's `kicad-fab.toml`:

```toml
# kicad-fab-package settings for this repository
project_dir = "hw"
baseline_paths = ["release/pic_programmer_v1.0_macrofab.xlsx"]
baseline_label = "v1.0"
```

A fuller example, for a repository whose project lives in `hw/`, with a parts library submodule and a previous
release's BOM as the baseline:

```toml
project_dir = "hw"
name_template = "acme_v{revision}"
library_dir = "parts_library"
library_paths = ["footprints", "symbols"]
library_model_paths = ["3d_models"]
generator_prefix = "tools/fab/"
require_dru = true
bom_csv = "hw/release/acme_bom.csv"
baseline_paths = ["release/archive/v1.1_macrofab.xlsx"]
baseline_label = "v1.1"
non_part_libs = ["Fiducial", "MountingHole", "parts_mech"]
require_filled_vias = true
```

The same as `kicad-fab.json`:

```json
{
  "project_dir": "hw",
  "name_template": "acme_v{revision}",
  "library_dir": "parts_library",
  "library_paths": ["footprints", "symbols"],
  "library_model_paths": ["3d_models"],
  "generator_prefix": "tools/fab/",
  "require_dru": true,
  "bom_csv": "hw/release/acme_bom.csv",
  "baseline_paths": ["release/archive/v1.1_macrofab.xlsx"],
  "baseline_label": "v1.1",
  "non_part_libs": ["Fiducial", "MountingHole", "parts_mech"],
  "require_filled_vias": true
}
```

Mistakes are reported before anything runs, with exit code 2 (local paths shortened):

```text
$ kicad-bom-check HEAD --config ../bad.json
ERROR: ~/boards/bad.json: unknown key(s) projct_dir; known: project_dir, name_template, library_dir, library_paths, library_model_paths, generator_prefix, require_dru, kicad_cli, kicad_python, kicad_3dmodel_dir, ibom_pkg, bom_csv, baseline_paths, baseline_label, revision_label, non_part_refs, non_part_libs, xyrs_non_part_refs, xyrs_non_part_libs, require_filled_vias, pcbway, pos_note_keeps
$ kicad-bom-check HEAD --config ../bad2.json
ERROR: ~/boards/bad2.json: non_part_libs must be a list of strings
$ kicad-bom-check HEAD --config ../bad3.toml
ERROR: ~/boards/bad3.toml: name_template '{board}_rev{revision}': only {project} and {revision} may be used ('board')
```

## All keys

| Key | Type | Default | Flag | Environment | Used by |
|---|---|---|---|---|---|
| [`project_dir`](#project_dir) | str | auto-detected | `--project-dir` |  | kicad-fab-export, kicad-macrofab-bom, kicad-bom-check, kicad-project-copy |
| [`name_template`](#name_template) | str | `{project}_v{revision}` | `--name-template` |  | kicad-fab-export, kicad-macrofab-bom |
| [`library_dir`](#library_dir) | str | none | `--library-dir` |  | kicad-fab-export, kicad-project-copy |
| [`library_paths`](#library_paths) | list | `[]` (whole library) | `--library-paths` |  | kicad-fab-export, kicad-project-copy |
| [`library_model_paths`](#library_model_paths) | list | `[]` (whole library) | `--library-model-paths` |  | kicad-fab-export |
| [`generator_prefix`](#generator_prefix) | str | `""` | `--generator-prefix` |  | kicad-fab-export, kicad-macrofab-bom |
| [`require_dru`](#require_dru) | bool | `false` | `--require-dru`, `--no-require-dru` |  | kicad-fab-export, kicad-macrofab-bom, kicad-bom-check, kicad-project-copy |
| [`kicad_cli`](#kicad_cli) | path | auto-detected | `--kicad-cli` | `KICAD_CLI` | kicad-fab-export, kicad-macrofab-bom, kicad-bom-check |
| [`kicad_python`](#kicad_python) | path | auto-detected | `--kicad-python` | `KICAD_PYTHON`, `KICAD10_PYTHON` | kicad-fab-export |
| [`kicad_3dmodel_dir`](#kicad_3dmodel_dir) | path | auto-detected | `--kicad-3dmodel-dir` | `KICAD10_3DMODEL_DIR` | kicad-fab-export |
| [`ibom_pkg`](#ibom_pkg) | path | none (no iBOM) | `--ibom-pkg` |  | kicad-fab-export |
| [`bom_csv`](#bom_csv) | str | none | `--csv` (kicad-bom-check) |  | kicad-bom-check |
| [`baseline_paths`](#baseline_paths) | list | `[]` | `--baseline`, `--no-baseline` override it |  | kicad-macrofab-bom |
| [`baseline_label`](#baseline_label) | str | `baseline` | `--baseline-label` |  | kicad-macrofab-bom |
| [`revision_label`](#revision_label) | str | `v{revision}` | `--revision-label` |  | kicad-macrofab-bom |
| [`non_part_refs`](#non_part_refs) | regex | `^(FID\|H)\d+$` | `--non-part-refs` |  | kicad-fab-export, kicad-macrofab-bom |
| [`non_part_libs`](#non_part_libs) | list | `["Fiducial", "MountingHole"]` | `--non-part-libs` |  | kicad-fab-export, kicad-macrofab-bom |
| [`xyrs_non_part_refs`](#xyrs_non_part_refs) | regex | same as `non_part_refs` | `--xyrs-non-part-refs` |  | kicad-fab-export |
| [`xyrs_non_part_libs`](#xyrs_non_part_libs) | list | same as `non_part_libs` | `--xyrs-non-part-libs` |  | kicad-fab-export |
| [`require_filled_vias`](#require_filled_vias) | bool | `false` | `--require-filled-vias`, `--no-require-filled-vias` |  | kicad-fab-export |
| [`pcbway`](#pcbway) | bool | `false` | `--pcbway`, `--no-pcbway` |  | kicad-fab-export |
| [`pos_note_keeps`](#pos_note_keeps) | str | see below |  |  | kicad-fab-export |

On the command line, a list is a comma list (`--library-paths footprints,symbols`) and `""` gives an empty list or
clears a string.

## Keys

### `project_dir`

*str; default: auto-detected.* The project folder inside the repository, repo-relative; `"."` for the top level.
Auto-detection takes the folder of the only `.kicad_pro` that has a `.kicad_pcb` of the same name beside it, at the
commit; with none or several, the tools stop and ask for it.

```toml
project_dir = "hw"
```

### `name_template`

*str; default `{project}_v{revision}`.* The output `NAME` when `--name` is not given. `{project}` is the KiCad project
name and `{revision}` its `REVISION`: the board's `REVISION` property for `kicad-fab-export`, the project's
`REVISION` text variable (else the board property) for `kicad-macrofab-bom`. Only these two placeholders are allowed.
A template with `{revision}` on a project without a revision is an error (pass `--name`). `NAME` may use letters,
digits, `_`, `.` and `-`.

```toml
name_template = "acme_v{revision}"      # acme_v1.2
```

### `library_dir`

*str; default: none.* The part library, relative to the project folder: a git submodule, or a plain folder of the
same repository. Its files are added to the project copy at the same place relative to the project, and its 3-D
models are staged for the STEP export, so footprints that reference models as `${KIPRJMOD}/<library_dir>/...` get
them. `--library-dir ""` clears a configured value.

- **A submodule** is taken at the commit the board's revision points it at, so the copy matches the commit even when
  your submodule checkout has moved on. When a linked git worktree has an empty submodule, the main checkout's
  submodule is used.
- **A folder** of the repository is taken from the exported commit itself (`git archive`), like the project. It may
  sit beside the project folder: [kicad-project-template](https://github.com/aqsnyder/kicad-project-template) keeps the
  library at `hw/lib` next to the boards in `hw/<board>/`, which reach it as `${KIPRJMOD}/../lib` and its models as
  `${KIPRJMOD}/../lib/3d_models/<file>`. The folder must stay inside the repository.

```toml
library_dir = "parts_library"           # a submodule inside the project folder
```

```toml
# kicad-project-template: hw/<board>/ beside hw/lib/, for every board (pass --project-dir hw/<board>)
library_dir = "../lib"
library_model_paths = ["3d_models"]
```

### `library_paths`

*list of str; default `[]` (the whole library).* The folders of the library that go into the project copy.

```toml
library_paths = ["footprints", "symbols"]
```

### `library_model_paths`

*list of str; default `[]` (the whole library).* The folders of the library holding 3-D models, staged for the STEP.

```toml
library_model_paths = ["3d_models"]
```

### `generator_prefix`

*str; default `""`.* Put before the tool's file name wherever the outputs name the tool that wrote them (the XYRS
header, the drill report, the manifest's `generator`, the BOM reports), for example the path of a vendored copy in
your repository.

```toml
generator_prefix = "tools/fab/"         # "tools/fab/export_fab.py"
```

### `require_dru`

*bool; default `false`.* Require `<project>.kicad_dru` (custom design rules) in the project copy.

```toml
require_dru = true
```

### `kicad_cli`

*path; default: auto-detected; environment `KICAD_CLI`.* The `kicad-cli` executable. When neither the flag, the
variable nor the key is set, the newest standard install is used, then `kicad-cli` on `PATH`. A `kicad-cli` older
than KiCad 10 gets a warning.

```toml
kicad_cli = "/opt/kicad-10/bin/kicad-cli"
```

### `kicad_python`

*path; default: auto-detected; environment `KICAD_PYTHON` or `KICAD10_PYTHON`.* KiCad's bundled Python, the one that
can `import pcbnew`. `kicad-fab-export` runs it as a subprocess for one board query and for the iBOM. Default: next to
`kicad-cli`, then the standard install folders (and `/usr/bin/python3` on Linux).

```toml
kicad_python = "/opt/kicad-10/bin/python3"
```

### `kicad_3dmodel_dir`

*path; default: auto-detected; environment `KICAD10_3DMODEL_DIR`.* KiCad's 3-D model library, passed to `kicad-cli`
as `KICAD9_3DMODEL_DIR` and `KICAD10_3DMODEL_DIR` for the STEP export.

```toml
kicad_3dmodel_dir = "/usr/share/kicad/3dmodels"
```

### `ibom_pkg`

*path; default: none.* An unpacked [InteractiveHtmlBom](https://github.com/openscopeproject/InteractiveHtmlBom)
package folder: the folder holding `InteractiveHtmlBom/generate_interactive_bom.py`. It is run with KiCad's Python.
Without it the iBOM is skipped with a warning.

```toml
ibom_pkg = "~/src/InteractiveHtmlBom"
```

### `bom_csv`

*str; default: none.* The committed grouped BOM csv, repo-relative, that `kicad-bom-check` compares with (read at the
commit). `--csv` sets it on the command line. With it set, `kicad-bom-check` always compares; to export only, use a
config without it.

```toml
bom_csv = "hw/release/acme_bom.csv"
```

### `baseline_paths`

*list of str; default `[]`.* Baseline BOM xlsx files for `kicad-macrofab-bom`'s diff, project-relative; the first one
that exists at the commit is used, and none existing is an error. `--baseline REV:PATH` or `--baseline FILE` overrides
it; `--no-baseline` skips the diff.

```toml
baseline_paths = ["release/pic_programmer_v1.0_macrofab.xlsx"]
```

### `baseline_label`

*str; default `baseline`.* How the reports and the diff file name call the baseline: `v1.0` gives
`NAME_vs_v1.0.md` and "the as-built v1.0 BOM". It must be usable in a file name. The checks report mentions the
baseline in its row rules only when one is configured.

```toml
baseline_label = "v1.0"
```

### `revision_label`

*str; default `v{revision}`.* How the BOM diff calls the new build (`{project}`, `{revision}`); `NAME` when the
project has no revision.

```toml
revision_label = "rev {revision}"       # "(v1.0 -> rev 1.1)"
```

### `non_part_refs`

*regex; default `^(FID|H)\d+$`; `""` = none.* Designators of fiducials and mounting holes, matched from the start of
the designator. A symbol matching it (or [`non_part_libs`](#non_part_libs)) that has no MPN gets no BOM row when it is
Populate 0, and no XYRS row when it is excluded from the BOM.

```toml
non_part_refs = '^(FID|MH)\d+$'
```

### `non_part_libs`

*list of str; default `["Fiducial", "MountingHole"]`; `[]` = none.* Footprint libraries of fiducials and mounting
holes (the part of the footprint id before `:`), with the same use as [`non_part_refs`](#non_part_refs). The demo's
`P101`-`P106` are recognised this way.

```toml
non_part_libs = ["Fiducial", "MountingHole", "parts_mech"]
```

### `xyrs_non_part_refs`

*regex; default: the value of `non_part_refs`.* `non_part_refs` for the XYRS only. Leave it unset so the XYRS and
the BOM leave out the same parts (MacroFab needs both to carry the same designators).

### `xyrs_non_part_libs`

*list of str; default: the value of `non_part_libs`.* `non_part_libs` for the XYRS only; leave it unset for the same
reason.

### `require_filled_vias`

*bool; default `false`.* Fail the two filled-via drill checks on a board with no filled-and-capped vias, for a design
that must have them (via-in-pad, for example).

```toml
require_filled_vias = true
```

### `pcbway`

*bool; default `false`.* `kicad-fab-export` also writes the PCBWay assembly files: the BOM xlsx in PCBWay's template
layout, a centroid csv per side, and a Gerber zip. They are derived from the same rows as the XYRS and cross-checked
against it; the MacroFab files are the same with or without them. See [PCBWay](pcbway.md).

```toml
pcbway = true
```

### `pos_note_keeps`

*str; default: "the parts excluded from the BOM but not DNP (test points, for example), fiducials and mounting
holes".* The words the manifest's note on `NAME_pos.csv` uses for what KiCad's `--exclude-dnp` position file still
keeps. Set it to name your board's parts.

```toml
pos_note_keeps = "the test points TP1-TP8, the programming header J5, and the fiducials"
```
