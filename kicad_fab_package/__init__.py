"""KiCad 10 fabrication and assembly package tools for MacroFab.

Commands (console scripts; each also runs as `python -m kicad_fab_package.<module>`):

  kicad-fab-export     export_fab          Gerbers, drills (filled vias split out), XYRS, pos, assembly PDF, iBOM,
                                           schematic PDF, STEP, ODB++, the MacroFab upload zip and a manifest; with
                                           --pcbway also PCBWay's BOM, centroid files and Gerber zip
  kicad-macrofab-bom   make_macrofab_xlsx  MacroFab per-designator BOM xlsx, grouped / per-reference csvs, reports
  kicad-bom-check      bom_check           regenerate the grouped BOM csv of a commit and compare it
  kicad-bomdiff        bomdiff             per-reference diff of two BOM csvs
  kicad-project-copy   kproject            a checked KiCad project copy of a commit, outside the repo

Library modules: kproject (project copies), sexp (s-expression parser), config (settings and KiCad detection),
models3d (3-D models of a library: a submodule or a folder of the repository).
"""
__version__ = '0.1.0'

COMMANDS = (
    ('kicad-fab-export', 'export_fab'),
    ('kicad-macrofab-bom', 'make_macrofab_xlsx'),
    ('kicad-bom-check', 'bom_check'),
    ('kicad-bomdiff', 'bomdiff'),
    ('kicad-project-copy', 'kproject'),
)
