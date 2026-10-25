# MacroFab walkthrough

From a finished package to a MacroFab order. The package side (file names, checks, counts) is exact; it is what
this tool writes. **Everything about MacroFab's web interface is as of 2026-10-25**: screen, tab and button names
change, so treat them as directions rather than labels, and take MacroFab's own help center and support as the
authority. This project is independent of MacroFab.

The examples use the demo's v1.1 package (`~/boards/fab/v1.1`, see [the examples](index.md#the-examples-in-these-pages)).

## 0. Before you upload

- Both commands exited 0, on the **same commit**, and that commit is on a branch or tag (no
  `source commit is on a branch or tag` warning).
- You read every `WARN` and `NOTE` line of the export summary (they are also in the manifest's `checks` and `notes`).
- The upload zip includes the BOM: the last check lines read
  `xlsx vs XYRS: same designators (57), unique, same Populate` and
  `upload zip: 14 members, CRC ok, byte-identical to the package files, no PDF / ODB++ / gbrjob`.
- Optional: pin the reviewed counts with `--expect` (see [getting started](getting-started.md#6-after-the-export)),
  and keep the manifest: its `commit` and the zip's `sha256` identify exactly what you sent.

## 1. Create a new PCB

As of 2026-10-25: in the MacroFab platform, create a new PCB (a new design) and name it after the package `NAME`
(`pic_programmer_v1.1`), so the order, the files and the manifest share one name. For a new revision of an existing
design, MacroFab's file import (FabIQ, announced by MacroFab in March 2026) asks whether to **replace all design
files** or **add only some**: replace them all, since the package is complete and every file in it belongs together.

## 2. Upload the zip

Upload `pic_programmer_v1.1_macrofab_upload.zip` as it is. It holds exactly the files MacroFab reads, flat, each name
with one dot before the extension that identifies the layer:

```text
pic_programmer_v1_1.GTL   pic_programmer_v1_1.GBL                    copper, top and bottom
pic_programmer_v1_1.GTP   pic_programmer_v1_1.GBP                    paste
pic_programmer_v1_1.GTO   pic_programmer_v1_1.GBO                    silkscreen
pic_programmer_v1_1.GTS   pic_programmer_v1_1.GBS                    solder mask
pic_programmer_v1_1.BOR                                              board outline (Edge.Cuts)
pic_programmer_v1_1_PTH.XLN  pic_programmer_v1_1_PTH_FILLED.XLN  pic_programmer_v1_1_NPTH.XLN   drills
pic_programmer_v1_1.XYRS                                             placement
pic_programmer_v1_1_macrofab.xlsx                                    BOM
```

PDFs, ODB++, the STEP model and the Gerber job file are deliberately not in it. Keep them for the DFM review: the
assembly PDF and the STEP model are what you send when MacroFab asks a placement or mechanical question.

## 3. Confirm Files: the layer mapping

As observed on 2026-10-25, the upload opens an import wizard. Its first step lists the files it took for a BOM (the
xlsx; keep it). The next step, **Confirm Files**, lists every other file with the layer type MacroFab detected and lets
you change a type or leave a file out; the drill files also get their plating and fill options there (next section).
**Import** then writes the files into the PCB version. Check every Gerber and drill row against
`fab/NAME_layer_map.csv`:

| Upload file | Must be mapped to |
|---|---|
| `BASE.GTL` | top copper |
| `BASE.G2L`, `BASE.G3L`, ... | inner copper layers, in order (a `G<n>P` file is a negative plane) |
| `BASE.GBL` | bottom copper |
| `BASE.GTS`, `BASE.GBS` | top / bottom solder mask |
| `BASE.GTO`, `BASE.GBO` | top / bottom silkscreen (legend) |
| `BASE.GTP`, `BASE.GBP` | top / bottom solder paste |
| `BASE.BOR` | board outline |
| `BASE_PTH.XLN` | plated drill |
| `BASE_PTH_FILLED.XLN` | plated drill (the filled vias; see the next step) |
| `BASE_NPTH.XLN` | non-plated drill |
| `BASE.XYRS` | placement (XYRS) |

Also check the layer count MacroFab derives from the copper files (2 for the demo), and look at the board in
MacroFab's viewer: the drills must sit on their pads (the export already checked that every plated hit sits on a
copper flash, so a visible offset means a mapping problem on MacroFab's side, not in the files).

## 4. The Vias tab: the filled-via drill file

MacroFab marks via fill per drill file, which is why the export moves every via with `(filling yes) (capping yes)` in
the board into `BASE_PTH_FILLED.XLN`. As observed on 2026-10-25, each drill file has **Plated**, **Filled/Plugged**
and a fill-material choice in the Confirm Files step, and the result shows afterwards on the PCB's **Vias** tab (under
the PCB design pages). Set:

| Drill file | Plated | Filled/Plugged | Fill |
|---|---|---|---|
| `BASE_PTH.XLN` | yes | no | |
| `BASE_PTH_FILLED.XLN` | yes | yes | Non-Conductive |
| `BASE_NPTH.XLN` | no | no | |

There was no separate **capping** option, so if you need IPC-4761 Type VII (filled, planarised and plated over, which
via-in-pad needs so the via cannot wick solder from the pad), ask for it in the DFM email and get it confirmed.

Check the counts against the drill report (`fab/NAME_drill_report.txt`), here 4 filled vias of 0.400 mm:

```text
    pic_programmer_v1.1_PTH_FILLED.drl: 4 holes
        T1  0.400  x4
```

If the option you need is not offered, say so in the [DFM email](#the-dfm-email) with the file name, the count and
the drill size. A board without filled vias still has a `_PTH_FILLED.XLN` file, with no holes; leave it unmarked (or
leave the file out in the Confirm Files step).

## 5. Specifications

Fill in the board specification from your design, not from defaults: board thickness, copper weights, surface finish,
solder mask and silkscreen colours, and the minimum features your board uses. MacroFab's import can read stack-up
details from a PDF you upload with the files (as of 2026-10-25); the package does not include a stack-up PDF, so
either enter them by hand or add your own PDF.

MacroFab also measures the design itself from the Gerbers and drills (minimum copper spacing and width, copper to
edge, smallest drill) and may switch the manufacturing class (for example to Extended / Extended Drill) to match. Its
readings can be smaller than your DRC rules allow, for instance where it measures between features of the same net.
If a reading looks wrong, ask where it is in the DFM email rather than changing the design.

## 6. The BOM: xlsx upload and column mapping

As observed on 2026-10-25, the xlsx in the zip is taken as the BOM file. Until you accept it, the PCB's **Bill of
Materials** tab shows lines built from the XYRS, which carries Value, Footprint, Populate and MPN. Opening the tab then
shows an **Import Bill of Materials** dialog with the columns already mapped and a preview (Populate shows as a
checkbox). Check the mapping and the Populate boxes of your Populate 0 parts, then **Accept Mapped Columns**; the BOM
is re-imported and matched against MacroFab's part market. If the BOM was not picked up from the zip, upload
`bom/NAME_macrofab.xlsx` on that tab. MacroFab's help center describes the BOM upload as an `.xlsx` file in which the
designator and the manufacturer part number are required and value, package and populate are optional. The mapping:

| xlsx column | MacroFab field |
|---|---|
| `Designator` | designator |
| `Value` | value |
| `Footprint` | package |
| `Populate` | populate (1 = place, 0 = do not place) |
| `MPN` | manufacturer part number |
| `Manufacturer` | manufacturer |

The xlsx has one designator per row, so every designator carries its own Populate and MPN. Upload the XYRS and the
xlsx from the **same run**: the XYRS and the BOM must carry the same designators, and an XYRS upload removes BOM rows
it does not contain. The export refuses to pack a zip whose xlsx and XYRS disagree.

After the import, read every line's matched part, not just the totals: manufacturer, stock and lead time. MacroFab
matches each MPN against its market and can pick the wrong maker for a generic part number. Seen on 2026-10-25: a
0 ohm resistor whose xlsx row said its real maker came back under another maker, with no stock and no price. Fix such
a line in its parts panel (next sections): search the MPN, **Add Component** for the right maker, then delete the
wrong entry.

## 7. Line grouping and Populate

MacroFab shows the BOM as lines, each holding several designators. Older MacroFab material describes grouping by
Value + package; on 2026-10-25 the lines observed were grouped by MPN (designators with the same MPN but a different
Value text stayed on separate lines), and after the xlsx was accepted the Populate 0 designators of a mixed group sat
on a line of their own. Grouping is MacroFab's to change, so check the two risky cases after every import; the BOM
checks report (`bom/NAME_bom_checks.md`) lists both before you upload:

- **Value + footprint collisions**: fitted parts with the same Value and footprint but different MPNs (the demo's
  v1.1 has `R5` at `DEMO-R-10K-1PCT` among `R1`-`R4`, `R6`-`R7` at `DEMO-R-10K`). Check that each of these
  designators kept its own MPN.
- **Mixed-Populate groups**: fitted and Populate 0 parts with the same Value and footprint (the demo's v1.0 has `R21`,
  DNP, among the fitted `R12`-`R14`). Check every Populate 0 designator by name: it must still be Do Not Place, and
  the fitted ones must still be fitted. A line's quantity (places x boards) is a quick cross-check.

Also check the **DNP / DNM text** flag: MacroFab announced in 2016 that DNP or DNM in a part's Value or MPN turns its
population off. A fitted part whose Value or MPN contains those letters is listed in the report; check it is still
populated after the import.

`MF-` part numbers are MacroFab house parts; the report lists them so you know which lines MacroFab supplies from its
own stock.

## 8. Approved alternates and line priority

The xlsx carries exactly one MPN per designator: the part you designed with. Alternates are decided on MacroFab's
side. MacroFab's help center describes two ways: an `.xlsx` with several MPN columns, and a reusable list of alternate
parts tied to a customer part number, kept under your organization.

As observed on 2026-10-25, each BOM line also has a parts panel (the search icon next to the line's manufacturer):

- **Parts Allowed** lists the parts MacroFab may build that line with; a check mark shows the one it will use
  (**To Be Built With**), with stock, price, preferred-vendor flag and lead time per part.
- **Priority**: **Price** takes the cheapest allowed part with stock; **Fixed** uses your order (arrows reorder the
  rows). Adding a component switched the line to Fixed in the session observed. Set Fixed, with only the designed
  part, on every line that must not be substituted.
- **Add Component** searches MacroFab's market by MPN (stock and price per maker); **Suggested Alternates** lists
  MacroFab's own suggestions; the trash icon removes an allowed part.

Whichever way you add alternates:

- keep the designed-in MPN as the line's first (primary) part, so the order and the BOM diff of the next release
  still describe the same board;
- add alternates per line, in order of preference, only when they are truly interchangeable (footprint, value,
  tolerance, voltage, temperature coefficient), and check which part MacroFab shows as chosen for each line before
  you approve the quote;
- record the policy in the [DFM email](#the-dfm-email) ("alternates allowed on lines X, Y; no substitutions
  elsewhere").

The next release's `NAME_vs_LABEL.md` lists the baseline's alternates if you diff against a BOM exported from
MacroFab with alternate columns.

## 9. Consigned parts

Parts you send to MacroFab yourself (a programmed device, a custom connector, a part on long lead time) stay in the
BOM as normal fitted rows (`Populate 1`, with their MPN): Populate 0 means "do not place", not "we supply it".

As observed on 2026-10-25, the source of each line is chosen on the **Quote & Order** page, in the **Sourcing**
column (**MacroFab** or **Me**). That choice was not kept when the page was reloaded: MacroFab's help says the parts
you supply are allocated after payment, on a **Parts to Supply** page, and the order overview then gives shipping
instructions. MacroFab's published packaging rules for consigned parts: original manufacturer packaging (cut tape
in an ESD bag is fine, loose parts taped together are not), no damaged parts, parts within their expiry date,
desiccant, and a humidity indicator card for MSL 2 and above. List the consigned lines in the DFM email with the
quantity you will ship, including spares for setup and attrition.

## 10. Part placement

The **Part Placement** page draws your XYRS over the board for each side (**Top View** / **Bottom View**), with a
designator search, a crosshair on the selected part, and **Nudge Parts**, which moves every part on one side by a step.
Use Nudge only for a uniform offset (a board-origin mismatch); a single wrong part means a wrong rotation or reference
point, so ask instead. Check the bottom side first, then connectors and modules with a large body offset
(`xyrs_body_offsets` in the manifest). As of 2026-10-25 there is no approve button: MacroFab dropped the placement
confirmation step from its web flow in March 2023 (its API still has a placement-approve call).

## 11. Parts MacroFab cannot source

When the quote page reports components missing availability, **Request Part Sourcing** (at the bottom of the Quote &
Order page) hands those lines to MacroFab's buyers. As observed on 2026-10-25 it opens a review with the lead time,
the order quantity, the order price without the requested parts and a notes field per part, then **Submit Request**;
MacroFab says to contact support if there is no reply within 24 business hours. Use the notes to pin what is
acceptable (exact MPN only, authorized or traceable sources, the quantity you may need). Set any part you will
supply yourself to **Me** in the same visit, right before **Request Part Sourcing**, and check that the review lists
only the lines MacroFab should buy (the **Me** choice did not survive a reload; see
[consigned parts](#9-consigned-parts)).

## The DFM email

Most of an order's open questions are answered by facts the export already printed. A useful email carries:

- **What it is**: `NAME`, the commit (the manifest's `commit` and `subject`), and the zip's sha256 (the manifest's
  `upload_zip.sha256`).
- **Filled vias**: the file, the count and the drill (`pic_programmer_v1_1_PTH_FILLED.XLN: 4 vias, 0.400 mm, IPC-4761
  Type VII`), and whether the fill option you chose includes capping.
- **Design-rule readings**: any MacroFab-measured minimum (spacing, copper to edge) that is below your DRC rules, so
  they can say where it is.
- **Silkscreen under 5 mil**: the `NOTE: Silk strokes under 0.127 mm ...` line, so nobody is surprised when thin lines
  are widened or dropped.
- **Paste you accepted on unplaced parts**: every `--accept-dnp-paste` part ("no paste at JP1").
- **Placement notes**: the bottom-side parts and the rotation rule used (KiCad orientation + 180), and the parts with
  a large body offset (`xyrs_body_offsets`), usually connectors.
- **BOM notes**: mixed-Populate groups and collisions to keep ungrouped, house parts, consigned parts, the
  alternates policy.

For the demo's v1.1 package that becomes, using only what the run printed:

```text
Subject: pic_programmer_v1.1 - DFM notes

Design: pic_programmer_v1.1, commit b483688d28daebc07c24cb37568099d18ee140c1
("pic_programmer 1.1: R18 330R, R21 fitted, R5/R10 MPNs").
Upload: pic_programmer_v1.1_macrofab_upload.zip (14 files).

- Filled vias: pic_programmer_v1_1_PTH_FILLED.XLN holds 4 vias, 0.400 mm, to be filled and capped
  (IPC-4761 Type VII). pic_programmer_v1_1_PTH.XLN is ordinary plated holes.
- Silkscreen: 386 strokes on the top and 4 on the bottom are 0.120 mm (under your 0.127 mm minimum);
  widen or drop them as you prefer.
- Placement: no bottom-side fitted parts; JP1 (bottom) is not placed. J1 and P3 bodies sit 6.2 mm and
  7.2 mm off their pad-pattern centres (the XYRS uses the pad-pattern centre).
- BOM: R5 (DEMO-R-10K-1PCT) shares Value + package with R1-R4, R6-R7 (DEMO-R-10K): please keep R5 on
  its own line. MF-TEST-0001 (C6, C7) is a MacroFab house part.
- Alternates: none without asking.
```
