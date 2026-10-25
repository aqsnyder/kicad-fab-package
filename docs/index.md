# kicad-fab-package documentation

kicad-fab-package turns one git commit of a KiCad 10 project into the files an assembly house needs, checks them
against each other and against the design, and packs the upload for [MacroFab](https://macrofab.com).

| Command | What it does | Page |
|---|---|---|
| `kicad-fab-export` | Gerbers, drills (filled vias split out), XYRS, position file, assembly / schematic PDFs, STEP, ODB++, iBOM, the upload zip and a manifest | [export-fab.md](export-fab.md) |
| `kicad-macrofab-bom` | MacroFab BOM xlsx, grouped and per-reference BOM csvs, a diff against a baseline BOM, a checks report | [bom.md](bom.md) |
| `kicad-bom-check` | regenerate a commit's grouped BOM csv with a fixed recipe and compare it with a committed or local csv | [bom.md](bom.md#kicad-bom-check) |
| `kicad-bomdiff` | per-reference diff of two BOM csvs | [bom.md](bom.md#kicad-bomdiff) |
| `kicad-project-copy` | a checked KiCad project copy of a commit (also the library module the other tools use) | [cli.md](cli.md#kicad-project-copy) |

## Pages

1. [Getting started](getting-started.md): install, the first run on a project in git, what lands where.
2. [kicad-fab-export](export-fab.md): every output file, every check and what a FAIL means, the manifest format, the
   upload zip and its naming, and the deliberate behaviours.
3. [MacroFab walkthrough](macrofab.md): from the upload zip to an order: layer mapping, the filled-via drill file,
   specifications, the BOM upload, line grouping and Populate, alternates, consigned parts and the DFM email.
4. [XYRS placement format](xyrs.md): units, origin, position, rotation, sides, types and body offsets, with a worked
   example.
5. [BOM tools](bom.md): the xlsx columns and row rules, the checks report, mixed-Populate groups, `kicad-bom-check`
   and `kicad-bomdiff`.
6. [CLI reference](cli.md): every command, argument, default, environment variable and exit code.
7. [Configuration](configuration.md): the config file and every key.
8. [Troubleshooting / FAQ](troubleshooting.md): real error messages and their fixes.

## The examples in these pages

Every output shown in these pages was produced by the commands next to it, with kicad-fab-package 0.1.0 and
KiCad 10.0.7 on Windows, on copies of KiCad's bundled `pic_programmer` demo project committed into scratch git
repositories:

- `~/boards/pic_programmer` holds a copy prepared to look like a real order: an `MPN` and a `Manufacturer` field on
  every part (synthetic `DEMO-...` part numbers, one `MF-` house part), a `REVISION` text variable, one part made
  DNP, four filled-and-capped vias, Fab-layer designators on three footprints that lacked them, no 3-D model entries
  pointing at files the demo does not ship, and plot settings without Protel extensions or X2 attributes. Tags
  `v1.0` and `v1.1` are two "releases".
- `~/boards/pic_programmer_raw` holds the demo exactly as KiCad ships it, to show what the checks say about a
  project that is not ready to order.

Outputs are trimmed where marked (`...`) and local paths are shortened to `~/boards/...` with forward slashes. Commit
hashes and file sizes are the real ones from that run.

## The short version

```bash
pip install git+https://github.com/aqsnyder/kicad-fab-package
cd my-board-repo                                   # one KiCad 10 project, committed
kicad-macrofab-bom HEAD --out ../fab/v1.0/bom      # BOM xlsx (+ csvs, checks report)
kicad-fab-export   HEAD --out ../fab/v1.0          # everything else + the upload zip
```

Exit code `0` means every error-level check passed; read the warnings anyway, they are short.
