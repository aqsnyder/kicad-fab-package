# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `kicad-fab-export --pcbway` (config key `pcbway`): PCBWay's assembly files next to the MacroFab ones, which do not
  change. `assembly/NAME_pcbway_bom.xlsx` uses the headers of PCBWay's BOM template (`Item #`, `*Designator`, `*Qty`,
  `Manufacturer`, `*Mfg Part #`, `Description / Value`, `*Package/Footprint`, `Type`, `Your Instructions / Notes`),
  one line per MPN + Manufacturer + Value + Footprint + Type with the designators in natural order. `Type` is `SMD` or
  `thru-hole` from the footprint attribute (the XYRS Type) and `DNS` for Populate 0, so a DNS part never shares a line
  with fitted ones. `assembly/NAME_pcbway_top.csv` and `NAME_pcbway_bottom.csv` (`Designator, Mid X(mm), Mid Y(mm),
  Layer, Rotation`) hold the Populate 1 XYRS rows in mm, origin at the outline's bottom-left corner seen from the top,
  with KiCad's own rotation on both sides. `NAME_pcbway_gerbers.zip` holds the fab Gerbers and the PTH and NPTH drill
  files (the filled-via file only when it has holes). Each file is read back and checked against the XYRS, the
  centroid rotations against KiCad's position file. See `docs/pcbway.md`.
- `library_dir` can name a plain folder of the repository instead of a git submodule, beside the project folder too:
  `library_dir = "../lib"` for kicad-project-template's `hw/lib`, reached as `${KIPRJMOD}/../lib`. Its files come from
  the exported commit with `git archive` (`kicad-project-copy --worktree`: from the working tree), for the project copy
  and for the STEP's 3-D models, so `STEP: every placed part with a model entry gets a model` passes for parts whose
  models live there.

### Fixed

- `STEP: origin = XYRS corner` failed on a round board. The board-only STEP's extent came from its CARTESIAN_POINTs,
  and a board outline that is one circle is exported as a STEP CIRCLE: its centre and one seam point, so an 18.5 mm
  board read y 0..9.25. The extent now comes from the edges: their end points, the extremes that circle and arc edges
  pass through (in the edge's direction, so a shallow arc counts only its own bulge), and the control points of
  spline edges.

## [0.1.0] - 2026-10-25

Initial public release.

### Added

- `kicad-fab-export`: exports a MacroFab fabrication and assembly package from any commit of a KiCad 10 project
  in a git repository, from a `git archive` project copy (the working tree is never read or written):
  - Gerbers (X2 off, checked against an explicit pinned-flag plot), the Gerber job file cut to them, and a layer
    map;
  - Excellon drills with plated, non-plated and filled-and-capped vias (IPC-4761 Type VII) in separate files,
    the filled vias selected by the board's `(filling yes) (capping yes)` tokens, plus KiCad's drill maps and an
    extended drill report;
  - the MacroFab XYRS placement file (mils, bottom-left origin, pad-box centres, bottom-side rotation rule) and
    KiCad's position file;
  - a two-page assembly PDF, the schematic PDF, an InteractiveHtmlBom page, a STEP model and ODB++;
  - the flat MacroFab upload zip, with one-dot member names and reproducible member dates;
  - a manifest with the commands, counts, checks, paste findings, pad-1 offsets and the sha256 of every file.
- Cross-checks: outline vs Gerber extents, drill hits on copper flashes, filled vias found exactly once, schematic
  vs board (DNP, BOM exclusion, value, footprint, MPN), XYRS vs the KiCad position file, no solder paste on parts
  that are not placed (board and plotted Gerbers), designators printed on the assembly drawing, STEP origin and
  models, ODB++ components, iBOM contents, xlsx vs XYRS designators.
- `kicad-macrofab-bom`: the per-designator MacroFab BOM xlsx (shared strings, byte-reproducible with or without lxml
  installed: openpyxl is kept on Python's own XML writer unless `OPENPYXL_LXML` is set), the grouped and
  per-reference BOM csvs, an optional per-designator diff against a baseline BOM xlsx, and a checks report with
  string-hygiene flags (odd MPN characters, house parts, manufacturer-name variants, value + package collisions,
  groups that mix fitted and unfitted parts) that points at the MacroFab walkthrough for checking the BOM lines
  after the import.
- `kicad-bom-check`: regenerates a commit's grouped BOM csv with a fixed kicad-cli recipe and compares it with a
  committed or local csv.
- `kicad-bomdiff`: per-reference diff of two BOM csvs; a missing or unreadable file, a csv without a `Reference`
  column or a grouped BOM is a setup error (exit 2) with a one-line message.
- `kicad-project-copy`: a checked KiCad project copy of a commit (or of the working tree), with an optional
  library submodule. A library checkout (here and in `kicad-fab-export`'s 3-D models) is recognised by comparing
  folders, not path strings, so a path that reaches the tools in another spelling (case, slash style, a Windows
  short 8.3 name) still counts as that checkout.
- Configuration through command-line flags, environment variables and an optional `kicad-fab.toml` /
  `kicad-fab.json` file. Configurable fiducial / mounting-hole recognition for the XYRS and the BOM, an optional
  requirement that the board has filled vias, and the labels used in the reports.
- KiCad install detection on Windows, macOS and Linux (kicad-cli, its Python, its 3-D model library). The newest
  standard install is preferred over `kicad-cli` on `PATH`, and a `kicad-cli` older than KiCad 10 gets a warning on
  stderr.
- Documentation in `docs/` (getting started, the export and its checks, a MacroFab walkthrough, the XYRS format, the
  BOM tools, CLI and configuration references, troubleshooting), with examples produced on KiCad's `pic_programmer`
  demo project.
- Unit tests that need no KiCad, an integration test that runs the whole flow when KiCad 10 is installed, and a
  GitHub Actions workflow (Ubuntu and Windows, Python 3.9 and 3.12).

[Unreleased]: https://github.com/aqsnyder/kicad-fab-package/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aqsnyder/kicad-fab-package/releases/tag/v0.1.0
