# PCBWay

```text
kicad-fab-export REV --out DIR --pcbway
```

With `--pcbway` (or [`pcbway = true`](configuration.md#pcbway) in the config file), `kicad-fab-export` also writes
the files a PCBWay assembly order takes: a BOM in PCBWay's template layout, a centroid (pick-and-place) file per side,
and a Gerber zip. They come from the same run as the MacroFab package: the BOM and the centroid files are made from
the XYRS rows, so they carry the same parts at the same points, and each file is read back and checked against the
XYRS (and the centroid rotations against KiCad's own position file). The MacroFab files are the same with or without
`--pcbway`.

| File | What it is |
|---|---|
| `NAME_pcbway_gerbers.zip` | the fab Gerbers and drill files, for the PCB part of the order ([below](#the-gerber-zip)) |
| `assembly/NAME_pcbway_bom.xlsx` | the BOM, one line per part number ([below](#the-bom)) |
| `assembly/NAME_pcbway_top.csv`, `assembly/NAME_pcbway_bottom.csv` | the centroid files, one per side ([below](#the-centroid-files)) |

The examples below are from KiCad's `pic_programmer` demo as KiCad ships it (no MPN or Manufacturer fields, all
parts on top), committed into a scratch repository.

## The BOM

`assembly/NAME_pcbway_bom.xlsx` has one sheet with the headers of PCBWay's BOM template
([Sample_BOM_PCBWay.xlsx](https://www.pcbway.com/img/images/pcbway/Sample_BOM_PCBWay.xlsx)), in its order; `*`
marks the columns PCBWay requires:

| Column | Contents |
|---|---|
| `Item #` | the line number, 1, 2, ... |
| `*Designator` | the line's designators, joined with `, ` in natural order (`R1, R2, R10`) |
| `*Qty` | the number of designators on the line |
| `Manufacturer` | the symbol's `Manufacturer` field (else `MANUFACTURER`) |
| `*Mfg Part #` | the `MPN` field |
| `Description / Value` | the Value |
| `*Package/Footprint` | the footprint name, without its library |
| `Type` | `SMD`, `thru-hole` or `DNS` |
| `Your Instructions / Notes` | empty, for you to fill in |

```text
Item # | *Designator | *Qty | Manufacturer | *Mfg Part # | Description / Value | *Package/Footprint | Type | Your Instructions / Notes
1 | C1 | 1 |  |  | 100µF | CP_Axial_L18.0mm_D6.5mm_P25.00mm_Horizontal | thru-hole |
...
6 | C6, C7 | 2 |  |  | 100nF | C_Disc_D5.1mm_W3.2mm_P5.00mm | thru-hole |
...
36 | U6 | 1 |  |  | PIC_8_PINS | DIP-8_W7.62mm_Socket_LongPads | thru-hole |
37 | JP1 | 1 |  |  | JUMPER | SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm | DNS |
```

- **Rows.** The BOM holds the XYRS rows: every schematic part on the board except fiducials and mounting holes (the
  [`non_part_refs` / `non_part_libs`](configuration.md#non_part_refs) rule), board-only footprints and parts excluded
  from the board. These are the parts of the MacroFab BOM too.
- **Lines.** One line per MPN + Manufacturer + Value + Footprint + Type. The manufacturer's spelling is part of the
  line: `Yageo` and `YAGEO` make two lines (`kicad-macrofab-bom`'s checks report flags such variants).
- **Type** comes from the footprint's KiCad attribute, as the XYRS Type does: `thru-hole` for a through-hole footprint
  (XYRS Type 2), `SMD` for the rest. A schematic `Type` field is never read. A Populate 0 part (DNP, or excluded from
  the BOM) is `DNS`, so it never shares a line with fitted parts of the same part number; the `DNS` lines come after
  the fitted ones.
- The xlsx is written as the MacroFab BOM is (shared strings, dated with the commit), so a commit's BOM is
  byte-reproducible.

## The centroid files

`assembly/NAME_pcbway_top.csv` and `assembly/NAME_pcbway_bottom.csv` hold the Populate 1 parts of each side. A side
without fitted parts gets a file with the header line only.

```text
Designator,Mid X(mm),Mid Y(mm),Layer,Rotation
C1,24.3300,60.8330,Top,180
C2,23.4220,49.5300,Top,0
C3,60.4520,67.4700,Top,270
...
```

- **Position**: the XYRS point, the centre of the part's pad bounding box, converted to mm (XYRS mil x 0.0254, four
  decimals).
- **Origin and axes**: the bottom-left corner of the board outline (the Edge.Cuts centre line) seen from the top, X to
  the right, Y up, for both sides: a bottom part's X is not mirrored. That is the frame of
  [PCBWay's centroid how-to](https://www.pcbway.com/helpcenter/design_instruction/How_to_create_a_Centroid_File_from_Eagle__Altium_Sprint_Layout_and_ORCAD_.html)
  (origin at the lower-left corner from the top, both sides referenced from the top), and the XYRS's.
- **Rotation**: KiCad's footprint orientation as it is, on both sides, from 0 to below 360 with at most three decimals.
  The XYRS adds 180 on the bottom (MacroFab's rule); the centroid files do not. PCBWay's own KiCad plugin
  ([`plugins/process.py`](https://github.com/pcbway/PCBWay-Plug-in-for-Kicad)) also writes the orientation unchanged.
- **Layer**: `Top` or `Bottom`.

PCBWay's plugin places each part by its footprint origin, measured from the board's drill/place file origin. These
files use the pad-box centre from the outline corner instead, the point MacroFab gets, because the export checks that
point against KiCad's own position file and because many footprints (connectors, axial parts) have their origin on
pin 1 rather than at their centre.

## The Gerber zip

`NAME_pcbway_gerbers.zip` holds, flat and under their `fab/` names, the fab Gerbers (`fab/NAME_<layer>.gbr`, every
file of the layer map), `NAME_PTH.drl` and `NAME_NPTH.drl`, and `NAME_PTH_FILLED.drl` only when the board has
filled-and-capped vias. No placement, BOM, PDF, ODB++ or job file goes in. Member dates are the commit date.

```text
pic_programmer_v1.0_top_layer.gbr           66391  2026-01-02 03:04:04
pic_programmer_v1.0_bottom_layer.gbr       308856  2026-01-02 03:04:04
...
pic_programmer_v1.0_Edge_Cuts.gbr             809  2026-01-02 03:04:04
pic_programmer_v1.0_PTH.drl                  5099  2026-01-02 03:04:04
pic_programmer_v1.0_NPTH.drl                  522  2026-01-02 03:04:04
```

The layer files are the ones the MacroFab zip carries under MacroFab's extensions; see
[Gerbers](export-fab.md#gerbers) and [Drills and filled vias](export-fab.md#drills-and-filled-vias). When the board
has filled vias, the summary adds a `NOTE`: say on the order that the holes in `NAME_PTH_FILLED.drl` are filled and
capped. `--no-zip` leaves this zip out as well.

## Checks

Each PCBWay file is read back after it is written. The checks are listed with the others in
[export-fab.md](export-fab.md#pcbway-with---pcbway); on the demo:

```text
ok   PCBWay BOM: 37 lines for the 57 XYRS rows, each designator once, Qty = its designators, DNS = Populate 0, MPN / Value / Footprint / Type as in the XYRS
ok   PCBWay centroid: the Populate 1 XYRS rows, 56 top / 0 bottom, at the XYRS point x 0.0254 mm (max diff 0.0001 mm)
ok   PCBWay centroid vs KiCad pos: rotation = pos Rot and side = pos Side on all 56 shared parts (no +180 on the bottom)
ok   PCBWay Gerber zip: 11 members (9 Gerbers, PTH + NPTH drills), CRC ok, byte-identical to the fab files, no assembly or reference files
```

The manifest records the files under `pcbway`: the BOM's path and line counts, each centroid file's path and rows, and
the Gerber zip's path, members, size and sha256.
