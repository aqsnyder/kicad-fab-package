# The XYRS placement file

`assembly/NAME.XYRS` tells MacroFab where each part goes. It is the file MacroFab reads; KiCad's own position file
(`assembly/NAME_pos.csv`) is written next to it for reference only.

## Format

Plain ASCII text, tab-delimited, LF line ends. Header lines start with `#`; the last header line names the columns:

| # | Column | Contents |
|---|---|---|
| 1 | `Designator` | the reference, e.g. `R1` |
| 2 | `X-Loc` | X of the part's position, mil, 2 decimals |
| 3 | `Y-Loc` | Y of the part's position, mil, 2 decimals |
| 4 | `Rotation` | whole degrees, 0..359 |
| 5 | `Side` | `1` = top (F.Cu), `2` = bottom (B.Cu) |
| 6 | `Type` | `2` = through-hole (the footprint's KiCad *through hole* attribute), `1` = everything else (SMT) |
| 7 | `X-Size` | pad extents along the footprint's own X axis, mil |
| 8 | `Y-Size` | pad extents along the footprint's own Y axis, mil |
| 9 | `Value` | the symbol's Value |
| 10 | `Footprint` | the footprint name without its library prefix |
| 11 | `Populate` | `1` = place it, `0` = do not (DNP, or excluded from the BOM) |
| 12 | `MPN` | the symbol's `MPN` field (never the library id); DNP rows keep theirs |

## The frame

- **Units**: mils (1 mil = 0.0254 mm).
- **Origin**: the bottom-left corner of the board outline's bounding box, taken on the centre line of the Edge.Cuts
  strokes. Every coordinate is inside `0..W x 0..H` (a check).
- **Axes**: X to the right, Y up, both seen from the top. Bottom-side parts are **not** mirrored: their X is the
  same as seen from the top.
- **Position**: the centre of the bounding box of the part's pads, in the board frame, **not** the footprint origin.
  An axial resistor's KiCad origin is pad 1, a connector's is often a mounting peg; the pad-box centre is what
  MacroFab's own XYRS generator uses. The manifest lists the parts whose origin is
  more than 0.05 mm from the pad-box centre (most through-hole parts).
- **Rotation**: top side = the KiCad orientation; bottom side = KiCad orientation + 180, modulo 360. That is the rule
  of MacroFab's own XYRS generator. Check bottom-side pin 1 in MacroFab's placement view anyway (see [placement
  review data](#placement-review-data)).
- **Sizes**: the pad extents in the footprint's own (unrotated) frame: exact pad boxes when the footprint and every
  pad sit at a multiple of 90 degrees, the pad polygons otherwise.

## Which parts get a row

One row per schematic symbol whose footprint is on the board, in natural designator order (`C2` before `C10`), except:

- **fiducials and mounting holes**: excluded from the BOM, no MPN, and a designator matching
  [`xyrs_non_part_refs`](configuration.md#non_part_refs) (`FID1`, `H3` by default) or a footprint from a library in
  [`xyrs_non_part_libs`](configuration.md#non_part_libs) (`Fiducial`, `MountingHole` by default). The BOM xlsx leaves out
  the same parts, because MacroFab needs both files to carry the same designators (an XYRS upload deletes BOM rows it
  does not contain);
- **board-only footprints without pads** (logos) and **symbols excluded from the board**.

Everything left out is named in the header. `Populate 0` rows stay in the file, with their MPN, so the XYRS and the
BOM xlsx carry exactly the same designators.

## The header

The demo's v1.1 header:

```text
# MacroFab XYRS placement file: pic_programmer 1.1
# Source: pic_programmer ecad commit b483688d28daebc07c24cb37568099d18ee140c1 (pic_programmer 1.1: R18 330R, R21 fitted, R5/R10 MPNs), KiCad 10.0.7, export_fab.py
# Units mil. Origin = bottom-left corner of the board outline (Edge.Cuts centre line) = KiCad (73.6600, 139.7000) mm; X right, Y up; bottom-side X not mirrored. Board 6300.00 x 3900.00 mil.
# Position = centre of the pad bounding box. Rotation: top = KiCad orientation; bottom = KiCad orientation + 180 (mod 360).
# Side 1 = top (F.Cu), 2 = bottom (B.Cu). Type 1 = SMT, 2 = PTH (KiCad through-hole attribute). X/Y-Size = pad extents in the footprint frame.
# 57 rows: 56 Populate 1, 1 Populate 0 (DNP or not a purchased part). Not listed: P101, P102, P103, P104, P105, P106.
# Fiducials (not rows): none
#Designator	X-Loc	Y-Loc	Rotation	Side	Type	X-Size	Y-Size	Value	Footprint	Populate	MPN
```

The first line uses the board's `BOARD_NAME` property when it has one (the project name otherwise); the
`generator_prefix` setting goes in front of `export_fab.py` on the second line. Footprints whose reference starts
with `FID`, or whose footprint comes from KiCad's `Fiducial` library, are listed on the fiducials line with their side
and position (mil, XYRS frame). This line is for the reader only and does not follow `non_part_refs`, which also
covers mounting holes; whether a fiducial gets a row is decided by the rule in
[Which parts get a row](#which-parts-get-a-row).

## Worked example

Two parts of the demo: `R1`, an axial resistor on top, and `JP1`, a solder jumper on the bottom. KiCad's position
file gives their footprint origins in the absolute (Gerber) frame, where Y is negative:

```text
Ref,Val,Package,PosX,PosY,Rot,Side
"JP1","JUMPER","SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",148.082000,-97.790000,0.000000,bottom
"R1","10K","R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",87.630000,-118.110000,0.000000,top
```

The manifest gives the XYRS origin (the outline's bottom-left corner in KiCad millimetres, Y down) and, per part,
where pad 1 is relative to the XYRS point:

```text
xyrs_origin_kicad_mm: [73.66, 139.7]
R1  {'xyrs_rot': 0, 'side': 1, 'pad1_offset_mil': [-200.0, 0.0], 'pad1_gerber_mm': [87.63, -118.11]}
JP1 {'xyrs_rot': 180, 'side': 2, 'pad1_offset_mil': [-28.54, 0.0], 'pad1_gerber_mm': [147.357, -97.79]}
```

`R1`'s origin is pad 1; its pads span 10.16 mm, so the pad-box centre is 5.08 mm (200 mil) to the right of it, at
KiCad (92.71, 118.11) mm. `JP1`'s origin is already its pad-box centre, (148.082, 97.79). The two transforms are
plain Python functions in the package:

```text
$ python -c "
from kicad_fab_package.export_fab import xyrs_point, xyrs_rotation
origin = (73.66, 139.7)                      # bottom-left corner of the outline, KiCad mm
print(xyrs_point(87.63 + 200 * 0.0254, 118.11, origin), xyrs_rotation(0, 1))   # R1, top
print(xyrs_point(148.082, 97.79, origin), xyrs_rotation(0, 2))                 # JP1, bottom
"
(749.9999999999999, 849.9999999999997) (0, 0)
(2930.0, 1649.9999999999993) (180, 180)
```

- `R1`: X = (92.71 - 73.66) / 0.0254 = 750.00 mil, Y = (139.70 - 118.11) / 0.0254 = 850.00 mil; top side, so the
  rotation is KiCad's 0.
- `JP1`: X = (148.082 - 73.66) / 0.0254 = 2930.00 mil, Y = (139.70 - 97.79) / 0.0254 = 1650.00 mil, not mirrored;
  bottom side, so the rotation is 0 + 180 = 180. It is excluded from the BOM, so `Populate` is 0 and the MPN is empty.

And the rows the export wrote:

```text
JP1	2930.00	1650.00	180	2	1	96.46	59.06	JUMPER	SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm	0
R1	750.00	850.00	0	1	2	462.99	62.99	10K	R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal	1	DEMO-R-10K
```

`R1`'s sizes are its pad pattern: 10.16 mm pitch plus one 1.6 mm pad = 11.76 mm = 462.99 mil long, 1.6 mm = 62.99
mil wide.

The export checks the same transform against KiCad's own position file on every part whose origin is its pad
centre, and the rotation rule on every part (`XYRS vs KiCad pos: ...` in the [checks](export-fab.md#placement)).

## Placement review data

Two manifest keys help review the placement in MacroFab's viewer:

- `xyrs_pad1`: for every row, the XYRS rotation and side, the offset of pad 1 (pad `1`, else `A1`) from the XYRS
  point in mil as seen from the top, and pad 1's Gerber-frame position. Compare the offset's direction with the
  pin-1 marker MacroFab shows, especially on the bottom side.
- `xyrs_body_offsets`: the rows whose courtyard-box centre (roughly the body) is more than 0.25 mm from the XYRS
  point, usually connectors and modules whose body overhangs their pads. The XYRS keeps the pad-pattern centre, as
  MacroFab's generator does; the body offset tells you where to expect the part outline to sit off-centre. From the
  demo:

  ```text
  NOTE: XYRS point vs courtyard-box (body) centre, parts more than 0.25 mm apart (the XYRS keeps the pad-pattern centre, as MacroFab's generator does): J1 [296.06, 985.83] -> body [50.79, 985.83] mil (6.23 mm); P3 [4300.0, 2611.81] -> body [4300.0, 2894.49] mil (7.18 mm); ...
  ```

## XYRS and KiCad's position file

| | `NAME.XYRS` | `NAME_pos.csv` |
|---|---|---|
| Units | mil | mm |
| Origin | outline bottom-left corner, Y up | absolute (the Gerber frame), so Y is negative |
| Position | pad-box centre | footprint origin |
| Bottom rotation | KiCad orientation + 180 | KiCad orientation |
| DNP parts | rows with `Populate 0` | left out (`--exclude-dnp`: a position file has no Populate column) |
| Excluded from BOM, not DNP | rows with `Populate 0` | kept |
| Fiducials, mounting holes | no row | kept (unless excluded from position files) |
| Used by MacroFab | yes | no |

The PCBWay centroid files that `--pcbway` adds are the XYRS's Populate 1 rows in mm, one file per side, with KiCad's
own orientation on the bottom (no +180): see [PCBWay](pcbway.md#the-centroid-files).
