#!/usr/bin/env python3
"""Export a commit's fab + assembly package for MacroFab (Gerber + Excellon + XYRS upload) and its reference files.

usage: kicad-fab-export REV --out DIR [--repo DIR] [--project-dir DIR] [--name NAME] [--name-template T]
                        [--ibom-pkg DIR] [--no-zip] [--kicad-cli PATH] [--kicad-python PATH]
                        [--kicad-3dmodel-dir DIR] [--library-dir DIR] [--library-paths P1,P2]
                        [--library-model-paths P1,P2] [--generator-prefix P] [--[no-]require-dru]
                        [--[no-]require-filled-vias] [--non-part-refs RE] [--non-part-libs L1,L2]
                        [--xyrs-non-part-refs RE] [--xyrs-non-part-libs L1,L2] [--config FILE]
                        [--work DIR] [--keep-work] [--expect KEY=N,...] [--step-with-dnp] [--force]
                        [--accept-dnp-paste REFS]
       kicad-fab-export --zip-only --out DIR      (re-pack the upload zip, e.g. once bom/ holds the xlsx; also
                                                   refreshes the manifest's file hashes)

REV is any commit (a commit object on no branch works). The board, schematic and project come from a git-archive
project copy (as kicad-project-copy makes) in a temp folder. With a library submodule configured (--library-dir,
relative to the project folder), its files are added to the copy, and its 3-D models (--library-model-paths) at the
board's library gitlink are staged next to it (the main checkout's library is used when a linked worktree's
submodule is empty). Nothing in the repo is written. NAME defaults to the name template, '{project}_v{revision}'
({project} = the KiCad project name, {revision} = the board's REVISION property).

What lands in DIR (bom/ belongs to the BOM tool, kicad-macrofab-bom, and is only read here):

  fab/       NAME_<layer>.gbr      copper, F/B mask, F/B paste, F/B silkscreen, Edge.Cuts. kicad-cli
                                   --board-plot-params (the board's own plot settings; -l is ignored with it, so the
                                   other plotted layers are dropped). X2 off is checked in the board settings and
                                   in every file; if the board ever turns X2 or netlist attributes on, the layers are
                                   re-plotted with --no-x2 --no-netlist and the summary says so. Never --check-zones.
                                   Names: KiCad's minus the board-name prefix, made file-system safe
                                   ('L3 (+Sig2)' -> NAME_L3_Sig2.gbr); NAME_layer_map.csv maps every file.
             NAME_job.gbrjob       KiCad's job file, cut to the fab Gerbers and renamed to match.
             NAME_PTH.drl          Excellon, mm, decimal, absolute origin (= the Gerber frame), PTH and NPTH separate.
             NAME_PTH_FILLED.drl   the vias with (filling yes) (capping yes) in the board, moved out of the PTH file
             NAME_NPTH.drl           (MacroFab marks fill per drill file; IPC-4761 Type VII). Selected by the board
                                   tokens, never by tool size (a via drill can sit a few um from a pad drill).
             NAME_{PTH,NPTH}_drl_map.pdf, NAME_drill_report.txt   KiCad's map and report (before the split; the
                                   report gets a note and a per-file tool table of the three final files appended).
             NAME_odb.zip          ODB++ (reference only; never in the upload zip).
  assembly/  NAME.XYRS             MacroFab placement: tab-delimited, mils, origin = bottom-left corner of the
                                   Edge.Cuts centre line, X right / Y up, bottom X not mirrored; position = pad
                                   bounding-box centre; rotation top = KiCad orientation, bottom = orientation + 180
                                   (mod 360); Side 1/2; Type 2 = KiCad through-hole attribute, else 1; X/Y-Size = pad
                                   extents in the footprint frame (exact pad boxes when every angle is a multiple of
                                   90 degrees; the pad polygon otherwise). One row per schematic part except fiducials
                                   and mounting holes (excluded from the BOM, no MPN, and a designator matching
                                   --xyrs-non-part-refs or a footprint library in --xyrs-non-part-libs; by default
                                   FID*/H* or KiCad's Fiducial / MountingHole libraries, the same rule as the BOM
                                   xlsx: is_non_part). Populate 0 = DNP or excluded from BOM in the
                                   schematic; MPN = the schematic MPN field (never lib_id). The manifest also lists
                                   each row's pad-1 offset (mil, top view) and the parts whose courtyard-box centre is
                                   more than 0.25 mm from the XYRS point (connectors and modules whose body overhangs
                                   their pads, typically).
             NAME_pos.csv          kicad-cli pos: csv, mm, both sides, absolute origin (the Gerber frame, so Y is
                                   negative), raw KiCad rotation, --exclude-dnp (a pos file has no Populate column).
             NAME_assembly.pdf     page 1 F.Fab + Edge.Cuts, page 2 B.Fab + Edge.Cuts mirrored; title block, 1:1 on
                                   the board's sheet, DNP sketched and crossed out, black and white. Without pypdf:
                                   NAME_assembly_top.pdf and NAME_assembly_bottom.pdf instead (a warning).
             NAME_ibom.html        InteractiveHtmlBom (--ibom-pkg: the unpacked package dir; run with KiCad's python),
                                   pin 1 highlighted on every part.
  docs/      NAME_schematic.pdf    the whole hierarchy, built-in default colour theme.
             NAME.step             board + 3-D models (--subst-models), DNP parts left out (--step-with-dnp keeps
                                   them), origin = the XYRS corner, so the board spans 0..W x 0..H mm. Models resolve
                                   as in the repo checkout: ${KIPRJMOD}/<library-dir>/... and KiCad's own; a bare
                                   file name only for a part with no other model (no doubled bodies).
             NAME_export_manifest.json   revision, commands, counts, checks, layer map, sha256 of every output
                                   ("outputs") and of every other file in DIR ("other_files": bom/, README.md). Local
                                   paths are written as <repo>, <main-checkout>, <work>, <out>, kicad-cli, ...
  NAME_macrofab_upload.zip         exactly the upload, flat, with a dot-free base name U (NAME with '.' -> '_', e.g.
                                   myboard_v1_2) so each member has one dot, before its extension: the Gerbers as
                                   U.GTL/.G2L../.GBL/.GTS/.GBS/.GTO/.GBO/.GTP/.GBP/.BOR, the 3 Excellon files as
                                   U_PTH.XLN / U_PTH_FILLED.XLN / U_NPTH.XLN, U.XYRS, and bom/NAME_macrofab.xlsx as
                                   U_macrofab.xlsx if it exists (its designators must equal the XYRS's). No PDF, ODB++
                                   or gbrjob. The names inside fab/, assembly/ and bom/ keep NAME.

Checks (an error makes the exit code 1; a warning is only printed): X2 off; Gerbers identical to an explicit
pinned-flag plot; outline Gerber extents = the pcbnew centre-line box; every drill hit inside the outline and on a
copper flash on both outer layers; filled vias found exactly once (a board with none passes unless
--require-filled-vias); no slots in the drill files; XYRS inside 0..W x
0..H; board and schematic agree on DNP / BOM exclusion / value / footprint / MPN; Populate 1 = the kicad-cli BOM;
fitted parts have an MPN; ASCII fields; pos rows and frame; XYRS frame and rotation against the KiCad pos file;
NO PASTE ON A POPULATE 0 PART, checked twice: in the board (no pad on a paste layer and no footprint graphic on
F/B.Paste, e.g. a filled fp_poly exposed-pad window) and in the plotted paste Gerbers (no flash, region or draw inside
the part's pad box on its own side); every fitted SMT row has paste in its pad box (warning, a control);
--accept-dnp-paste REFS turns the paste error for those parts into a warning and a note (the fallback when the board
cannot change: tell MacroFab "no paste at REFS"); schematic page count; every XYRS designator printed on its assembly
page (PyMuPDF); STEP origin; 3-D models resolved; ODB++ components and filling layer; iBOM line count and refs; xlsx vs
XYRS; the upload member names; --expect counts (fitted, rows, pop0, fitted_top, fitted_bottom, pth, filled, npth,
pages). A warning, not an error: REV is on no branch or tag (a scratch commit; re-run on the final commit before the
outputs are committed, because REV is written into the XYRS header, the manifest and the zip dates).
Silk strokes thinner than 0.127 mm (MacroFab's 5 mil minimum) are counted per width (counts, not a check).
Exit 0 ok, 1 a step or check failed (the summary says which), 2 setup error. The temp folder is removed on success
unless --work or --keep-work is given.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
import xml.etree.ElementTree as ET

# KiCad's python runs this file as a plain script (-I) for --pcbnew-dump, which needs the standard library only
try:
    from . import config, kproject, models3d
except ImportError:
    config = kproject = models3d = None

TOOL = 'export_fab.py'
MIL = 0.0254
# the default non_part_refs / non_part_libs settings (config.NON_PART_REFS / NON_PART_LIBS)
NON_PART_RE = re.compile(r'^(FID|H)\d+$')      # fiducials and mounting holes: footprints with no part to buy
NON_PART_LIBS = ('Fiducial', 'MountingHole')    # ... and KiCad's footprint libraries for them
DNP_WORD_RE = re.compile(r'DN[PM]', re.I)       # MacroFab's 2016 rule: DNP/DNM in Value or MPN depopulates
NON_COPPER = {  # gbrjob FileFunction -> (KiCad layer, MacroFab extension)
    'SolderMask,Top': ('F.Mask', 'GTS'), 'SolderMask,Bot': ('B.Mask', 'GBS'),
    'Legend,Top': ('F.Silkscreen', 'GTO'), 'Legend,Bot': ('B.Silkscreen', 'GBO'),
    'SolderPaste,Top': ('F.Paste', 'GTP'), 'SolderPaste,Bot': ('B.Paste', 'GBP'),
    'Profile': ('Edge.Cuts', 'BOR'),
}
EXPECT_KEYS = ('fitted', 'rows', 'pop0', 'fitted_top', 'fitted_bottom', 'pth', 'filled', 'npth', 'pages')
DATE_LINE_RE = re.compile(r'CreationDate|Created by|^; DRILL file|date \d{4}-\d\d-\d\d')


# --------------------------------------------------------------------------------------------- pcbnew side
def pcbnew_dump(board_path, out_path):
    """Run by KiCad's python (-I): every board fact the package needs, as json."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    nm = 1e6

    def cast(item):
        return item.Cast() if hasattr(item, 'Cast') else item

    xs, ys = [], []
    items = [cast(d) for d in b.GetDrawings()]
    for fp in b.GetFootprints():
        items += [cast(g) for g in fp.GraphicalItems()]
    for d in items:
        if d.GetLayer() != pcbnew.Edge_Cuts or d.GetClass() != 'PCB_SHAPE':
            continue
        bb = d.GetBoundingBox()
        w2 = d.GetWidth() / 2.0
        xs += [bb.GetLeft() + w2, bb.GetRight() - w2]
        ys += [bb.GetTop() + w2, bb.GetBottom() - w2]
    if not xs:
        raise SystemExit('no Edge.Cuts shapes')
    out = {'edge_centreline_mm': [min(xs) / nm, min(ys) / nm, max(xs) / nm, max(ys) / nm]}
    ds = b.GetDesignSettings()
    out['aux_origin_mm'] = [ds.GetAuxOrigin().x / nm, ds.GetAuxOrigin().y / nm]
    out['grid_origin_mm'] = [ds.GetGridOrigin().x / nm, ds.GetGridOrigin().y / nm]
    out['copper_layers'] = b.GetCopperLayerCount()
    out['thickness_mm'] = ds.GetBoardThickness() / nm
    out['properties'] = {str(k): str(v) for k, v in dict(b.GetProperties()).items()}

    def right_angle(deg):
        return abs(deg / 90.0 - round(deg / 90.0)) < 1e-6

    def pad_shape(p, layer):
        try:
            return p.GetShape(layer)
        except TypeError:
            return p.GetShape()

    paste_layers = {pcbnew.F_Paste: 'F.Paste', pcbnew.B_Paste: 'B.Paste'}
    crtyd_layers = (pcbnew.F_CrtYd, pcbnew.B_CrtYd)

    def bbox_mm(item):
        bb = item.GetBoundingBox()
        return [bb.GetLeft() / nm, bb.GetTop() / nm, bb.GetRight() / nm, bb.GetBottom() / nm]

    out['board_paste_graphics'] = [{'layer': paste_layers[cast(d).GetLayer()], 'class': cast(d).GetClass(),
                                    'uuid': cast(d).m_Uuid.AsString(), 'bbox_mm': bbox_mm(cast(d))}
                                   for d in b.GetDrawings() if cast(d).GetLayer() in paste_layers]
    fps = []
    for fp in b.GetFootprints():
        ori = fp.GetOrientationDegrees()
        pos = fp.GetPosition()
        a = math.radians(ori)
        ca, sa = math.cos(a), math.sin(a)
        box = None
        lx, ly = [], []
        pth = npth = 0
        slots = []
        paste_pads = []
        pad1 = []
        size_src = collections.Counter()
        for p in fp.Pads():
            pb = p.GetBoundingBox()
            r = (pb.GetLeft(), pb.GetTop(), pb.GetRight(), pb.GetBottom())
            box = r if box is None else (min(box[0], r[0]), min(box[1], r[1]), max(box[2], r[2]), max(box[3], r[3]))
            layer = p.GetPrincipalLayer() if hasattr(p, 'GetPrincipalLayer') else p.GetLayer()
            pts = []
            # Exact extents: with the footprint and the pad at a multiple of 90 degrees, the board-frame bounding box
            # of a non-custom pad is its true outline box, so its corners de-rotate exactly. The ERROR_INSIDE polygon
            # is used only otherwise: it lies inside the true outline, so round pads read up to 0.4 mil short.
            if right_angle(ori) and right_angle(p.GetOrientationDegrees()) and \
                    pad_shape(p, layer) != pcbnew.PAD_SHAPE_CUSTOM:
                pts = [(r[0], r[1]), (r[2], r[3]), (r[0], r[3]), (r[2], r[1])]
                size_src['bbox'] += 1
            else:
                try:
                    poly = p.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE)
                    for k in range(poly.OutlineCount()):
                        ol = poly.Outline(k)
                        pts += [(ol.CPoint(i).x, ol.CPoint(i).y) for i in range(ol.PointCount())]
                    size_src['polygon'] += 1
                except Exception:
                    pts = []
                if not pts:
                    pts = [(r[0], r[1]), (r[2], r[3]), (r[0], r[3]), (r[2], r[1])]
                    size_src['bbox fallback'] += 1
            on_paste = [name for lid, name in paste_layers.items() if p.IsOnLayer(lid)]
            if on_paste:
                paste_pads.append([p.GetNumber()] + on_paste)
            if p.GetNumber() in ('1', 'A1'):
                pad1.append([p.GetNumber(), p.GetPosition().x / nm, p.GetPosition().y / nm])
            for qx, qy in pts:
                dx, dy = (qx - pos.x) / nm, (qy - pos.y) / nm
                lx.append(dx * ca - dy * sa)   # undo the footprint rotation (KiCad: y down, CCW on screen)
                ly.append(dx * sa + dy * ca)
            at = p.GetAttribute()
            if at == pcbnew.PAD_ATTRIB_PTH:
                pth += 1
            elif at == pcbnew.PAD_ATTRIB_NPTH:
                npth += 1
            dsz = p.GetDrillSize()
            if dsz.x > 0 and dsz.y > 0 and dsz.x != dsz.y:
                slots.append([p.GetNumber(), dsz.x / nm, dsz.y / nm])
        attrs = fp.GetAttributes()
        kind = 'TH' if attrs & pcbnew.FP_THROUGH_HOLE else ('SMD' if attrs & pcbnew.FP_SMD else 'unspecified')
        fields = {str(k): str(v) for k, v in dict(fp.GetFieldsShownText()).items()}
        paste_gfx, crt = [], None
        for g in fp.GraphicalItems():
            g = cast(g)
            lid = g.GetLayer()
            if lid in paste_layers:
                paste_gfx.append({'layer': paste_layers[lid], 'class': g.GetClass(), 'uuid': g.m_Uuid.AsString(),
                                  'bbox_mm': bbox_mm(g)})
            elif lid in crtyd_layers:
                gb = bbox_mm(g)
                crt = gb if crt is None else [min(crt[0], gb[0]), min(crt[1], gb[1]), max(crt[2], gb[2]),
                                              max(crt[3], gb[3])]
        # pad "1", else "A1"; with several pads of that number (pad1_count > 1) the first in footprint order is used
        pad1.sort(key=lambda q: q[0] != '1')   # stable: keeps footprint order within each number
        fps.append({
            'ref': fp.GetReference(), 'value': fields.get('Value', fp.GetValue()), 'fpid': fp.GetFPIDAsString(),
            'side': 'B' if fp.IsFlipped() else 'F', 'orientation': ori, 'pos_mm': [pos.x / nm, pos.y / nm],
            'pad_box_mm': [v / nm for v in box] if box else None,
            'pad_extent_local_mm': [min(lx), max(lx), min(ly), max(ly)] if lx else None,
            'kind': kind, 'dnp': bool(fp.IsDNP()), 'exclude_bom': bool(fp.IsExcludedFromBOM()),
            'exclude_pos': bool(fp.IsExcludedFromPosFiles()), 'board_only': bool(fp.IsBoardOnly()),
            'n_pads': len(fp.Pads()), 'pth_pads': pth, 'npth_pads': npth, 'slots': slots,
            'mpn': fields.get('MPN'), 'manufacturer': fields.get('Manufacturer', fields.get('MANUFACTURER')),
            'models': [{'file': m.m_Filename, 'show': bool(m.m_Show)} for m in fp.Models()],
            'pad_size_source': dict(size_src), 'paste_pads': paste_pads, 'paste_graphics': paste_gfx,
            'courtyard_box_mm': crt, 'pad1_mm': pad1[0][1:] if pad1 else None, 'pad1_count': len(pad1),
            'uuid': fp.m_Uuid.AsString(),
        })
    out['footprints'] = fps
    vias = []
    for t in b.GetTracks():
        if t.GetClass() != 'PCB_VIA':
            continue
        v = cast(t)
        rec = {'pos_mm': [v.GetPosition().x / nm, v.GetPosition().y / nm], 'drill_mm': v.GetDrillValue() / nm,
               'type': int(v.GetViaType())}
        for g in ('GetFillingMode', 'GetCappingMode'):
            try:
                rec[g] = str(getattr(v, g)())
            except Exception as e:  # noqa: BLE001
                rec[g] = 'ERR ' + type(e).__name__
        vias.append(rec)
    out['vias'] = vias
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)


# --------------------------------------------------------------------------------------------- helpers
class StepError(Exception):
    pass


class SetupError(Exception):
    pass


def is_non_part(ref, lib_id, refs=NON_PART_RE, libs=NON_PART_LIBS):
    """A fiducial or mounting hole, by designator (refs: a compiled regex matched from the start, or None for none;
    default FID1, H3) or by footprint library (libs; default KiCad's 'Fiducial:...', 'MountingHole:...'). The XYRS
    leaves such a symbol out when it is excluded from the BOM and has no MPN (the MacroFab BOM: Populate 0, no MPN)."""
    return bool(refs and refs.match(ref)) or (lib_id.split(':', 1)[0] if ':' in lib_id else '') in libs


def is_fiducial(ref, fpid):
    """A footprint listed on the XYRS header's fiducials line: a designator starting with FID, or a footprint from
    KiCad's Fiducial library. Independent of non_part_refs, which also covers mounting holes."""
    return ref.startswith('FID') or fpid.split(':', 1)[0] == 'Fiducial'


def filled_vias_seen(want_set, groups, required=False):
    """Drill check: pcbnew's filling/capping mode groups include one equal to the board-text set of filled vias.
    A board with no filled vias passes, unless they are required (require_filled_vias): then it fails."""
    return (not want_set and not required) or any(g == want_set for g in groups.values())


def filled_vias_found(unmatched, filled, required=False):
    """Drill check: every filled via matched exactly one PTH hit. A board with no filled vias passes, unless they are
    required (require_filled_vias): then it fails."""
    return not unmatched and (bool(filled) or not required)


def natural_key(ref):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', ref)]


def plural(n, word):
    """'1 part', '2 parts' (word is the singular; its last word takes the 's')."""
    return '%d %s%s' % (n, word, '' if n == 1 else 's')


def upload_base(prefix):
    """The upload members' base name: NAME without dots (myboard_v1.2 -> myboard_v1_2), so the only dot in each
    member name is the one before the extension that MacroFab identifies the layer by."""
    return prefix.replace('.', '_')


def fab_layer_stem(kicad_file, pname):
    """File-system safe layer part of a Gerber name: KiCad's file name without the '<project>-' prefix and the
    extension, every run of other characters made '_' ('myboard-L3 (+Sig2).gbr' -> 'L3_Sig2')."""
    stem = kicad_file[:-4] if kicad_file.endswith('.gbr') else os.path.splitext(kicad_file)[0]
    stem = stem[len(pname) + 1:] if stem.startswith(pname + '-') else stem
    return re.sub(r'[^A-Za-z0-9]+', '_', stem).strip('_')


def copper_upload_ext(n, where, polarity):
    """MacroFab extension of copper layer n ('Top', 'Bot' or 'Inr'): GTL, GBL, or G<n>L (G<n>P for a negative
    plane)."""
    return 'GTL' if where == 'Top' else ('GBL' if where == 'Bot' else 'G%d%s' % (n, 'L' if polarity == 'Positive'
                                                                                else 'P'))


def xyrs_rotation(orientation, side):
    """(raw, rounded) XYRS rotation of a part: top (side 1) = KiCad orientation, bottom (side 2) = orientation + 180,
    mod 360; rounded to whole degrees."""
    raw = orientation % 360 if side == 1 else (orientation + 180) % 360
    return raw, int(round(raw)) % 360


def xyrs_point(x_mm, y_mm, origin):
    """KiCad board mm (Y down) -> XYRS mil (Y up) from origin = (left, bottom) of the Edge.Cuts centre line."""
    x0, y1 = origin
    return (x_mm - x0) / MIL, (y1 - y_mm) / MIL


def upload_members(out, prefix, layer_map, base=None):
    """[(source path, member name)] of the upload zip, in upload order."""
    base = base or upload_base(prefix)
    members = [(os.path.join(out, 'fab', s['fab_file']), s['upload_file']) for s in layer_map]
    for kind in ('PTH', 'PTH_FILLED', 'NPTH'):
        members.append((os.path.join(out, 'fab', '%s_%s.drl' % (prefix, kind)), '%s_%s.XLN' % (base, kind)))
    members.append((os.path.join(out, 'assembly', '%s.XYRS' % prefix), '%s.XYRS' % base))
    xlsx = os.path.join(out, 'bom', '%s_macrofab.xlsx' % prefix)
    if os.path.exists(xlsx):
        members.append((xlsx, '%s_macrofab.xlsx' % base))
    return members


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def page_count(path):
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except ImportError:
        with open(path, 'rb') as f:
            return len(re.findall(rb'/Type\s*/Page(?![s\w])', f.read()))


def read_text(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def lz_decompress_b64(s):
    """LZString.decompressFromBase64 (the iBOM page stores its data this way). A Python port of lz-string's
    decompressor (lz-string: MIT License, Copyright (c) 2013 pieroxy, https://github.com/pieroxy/lz-string)."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
    vals = [alphabet.index(ch) for ch in s]
    if not vals:
        return ''
    reset = 32
    st = {'val': vals[0], 'pos': reset, 'idx': 1}

    def bits(n):
        r, power = 0, 1
        for _ in range(n):
            resb = st['val'] & st['pos']
            st['pos'] >>= 1
            if st['pos'] == 0:
                st['pos'] = reset
                st['val'] = vals[st['idx']] if st['idx'] < len(vals) else 0
                st['idx'] += 1
            if resb:
                r |= power
            power <<= 1
        return r

    dictionary = {}
    enlarge, size, nbits = 4, 4, 3
    first = bits(2)
    if first == 0:
        c = chr(bits(8))
    elif first == 1:
        c = chr(bits(16))
    else:
        return ''
    dictionary[3] = c
    w, out = c, [c]
    while True:
        if st['idx'] > len(vals):
            return ''
        c = bits(nbits)
        if c in (0, 1):
            dictionary[size] = chr(bits(8 if c == 0 else 16))
            size += 1
            c = size - 1
            enlarge -= 1
        elif c == 2:
            return ''.join(out)
        if enlarge == 0:
            enlarge, nbits = 1 << nbits, nbits + 1
        if c in dictionary:
            entry = dictionary[c]
        elif c == size:
            entry = w + w[0]
        else:
            raise ValueError('bad LZString data')
        out.append(entry)
        dictionary[size] = w + entry[0]
        size += 1
        enlarge -= 1
        w = entry
        if enlarge == 0:
            enlarge, nbits = 1 << nbits, nbits + 1


# --------------------------------------------------------------------------------------------- Gerber / Excellon
def gerber_ops(path):
    """(flashes, stroke points) of a KiCad RS-274X file in mm, Gerber frame (Y up). Arc extremes included."""
    dec, scale = 6, 1.0
    x = y = 0.0
    mode = 1
    flashes, pts = [], []
    op = re.compile(r'^(?:G0?([123]))?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0?([123])\*$')
    for ln in read_text(path).splitlines():
        ln = ln.strip()
        m = re.match(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%', ln)
        if m:
            dec = int(m.group(2))
            continue
        if ln == '%MOIN*%':
            scale = 25.4
        if re.match(r'^G0?([123])\*$', ln):
            mode = int(re.match(r'^G0?([123])\*$', ln).group(1))
            continue
        m = op.match(ln)
        if not m:
            continue
        if m.group(1):
            mode = int(m.group(1))
        nx = int(m.group(2)) / 10 ** dec * scale if m.group(2) is not None else x
        ny = int(m.group(3)) / 10 ** dec * scale if m.group(3) is not None else y
        d = int(m.group(6))
        if d == 3:
            flashes.append((nx, ny))
        elif d == 1:
            pts += [(x, y), (nx, ny)]
            if mode in (2, 3) and m.group(4) is not None:
                cx = x + int(m.group(4)) / 10 ** dec * scale
                cy = y + int(m.group(5) or 0) / 10 ** dec * scale
                r = math.hypot(x - cx, y - cy)
                a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
                start, end = (a0, a1) if mode == 3 else (a1, a0)      # sweep counter-clockwise from start
                sweep = (end - start) % (2 * math.pi) or 2 * math.pi
                for k in range(4):
                    ang = k * math.pi / 2
                    if (ang - start) % (2 * math.pi) <= sweep:
                        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        else:
            pts.append((nx, ny))
        x, y = nx, ny
    return flashes, pts


def gerber_objects(path):
    """Every graphic object of a KiCad RS-274X file, mm, Gerber frame (Y up):
    {'flashes': [(x, y, dcode, polarity)], 'regions': [(points, polarity)], 'draws': [(x0, y0, x1, y1, dcode,
    polarity)], 'apertures': {dcode: (template, [params])}}. A flash is kept as its centre (macro apertures are not
    expanded); a region as its contour vertices; a draw (D01 outside G36/G37, arcs included) as its two end points."""
    dec, scale = 6, 1.0
    x = y = 0.0
    cur, pol, in_region = None, 'D', False
    out = {'flashes': [], 'regions': [], 'draws': [], 'apertures': {}}
    contour = []
    op = re.compile(r'^(?:G0?[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0?([123])\*$')
    for ln in read_text(path).splitlines():
        ln = ln.strip()
        m = re.match(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%', ln)
        if m:
            dec = int(m.group(2))
            continue
        if ln == '%MOIN*%':
            scale = 25.4
            continue
        m = re.match(r'^%ADD(\d+)([A-Za-z_$][\w.$]*),?([^*]*)\*%$', ln)
        if m:
            out['apertures'][int(m.group(1))] = (m.group(2), [float(v) for v in m.group(3).split('X') if v])
            continue
        m = re.match(r'^%LP([CD])\*%$', ln)
        if m:
            pol = m.group(1)
            continue
        if ln.startswith('G36'):
            in_region, contour = True, []
            continue
        if ln.startswith('G37'):
            if len(contour) > 1:
                out['regions'].append((contour, pol))
            in_region, contour = False, []
            continue
        m = re.match(r'^(?:G54)?D(\d{2,})\*$', ln)
        if m and int(m.group(1)) >= 10:
            cur = int(m.group(1))
            continue
        m = op.match(ln)
        if not m:
            continue
        nx = int(m.group(1)) / 10 ** dec * scale if m.group(1) is not None else x
        ny = int(m.group(2)) / 10 ** dec * scale if m.group(2) is not None else y
        d = int(m.group(5))
        if in_region:
            if d == 2:
                if len(contour) > 1:
                    out['regions'].append((contour, pol))
                contour = [(nx, ny)]
            elif d == 1:
                contour = (contour or [(x, y)]) + [(nx, ny)]
        elif d == 3:
            out['flashes'].append((nx, ny, cur, pol))
        elif d == 1:
            out['draws'].append((x, y, nx, ny, cur, pol))
        x, y = nx, ny
    return out


def x2_attribute_lines(path):
    return sum(1 for ln in read_text(path).splitlines() if re.match(r'^%T[FAOD]', ln.strip()))


class Excellon:
    """A KiCad Excellon file split into header (pre-tool lines, tool blocks), body per tool, and the rest."""

    def __init__(self, path):
        raw = read_text(path)
        self.eol = '\r\n' if '\r\n' in raw else '\n'
        lines = raw.splitlines()
        if '%' not in lines:
            raise StepError('%s: no header end (%%)' % path)
        cut = lines.index('%')
        self.pre, self.tools, pending = [], collections.OrderedDict(), []
        for ln in lines[:cut]:
            m = re.match(r'^T(\d+)C([\d.]+)', ln)
            if m:
                self.tools[int(m.group(1))] = {'dia': float(m.group(2)), 'lines': pending + [ln], 'hits': []}
                pending = []
            elif ln.startswith('; #@! TA.'):
                pending.append(ln)
            elif not self.tools:
                self.pre.append(ln)
            else:
                pending.append(ln)
        self.post_tools = pending
        self.body_pre, self.tail = [], []
        self.slot_lines = []
        cur = None
        x = y = None
        for ln in lines[cut + 1:]:
            s = ln.strip()
            m = re.match(r'^T(\d+)$', s)
            if m:
                cur = int(m.group(1))
                continue
            if re.search(r'G85|^G0[01]|^M1[56]', s):
                self.slot_lines.append(s)
            m = re.match(r'^(?:X(-?[\d.]+))?(?:Y(-?[\d.]+))?$', s)
            if s and m and (m.group(1) or m.group(2)):
                x = float(m.group(1)) if m.group(1) else x
                y = float(m.group(2)) if m.group(2) else y
                if cur is None or cur not in self.tools:
                    raise StepError('hit before a known tool: %s' % s)
                self.tools[cur]['hits'].append(((x, y), ln))
            elif cur is None:
                self.body_pre.append(ln)
            elif s == 'M30' or self.tail:
                self.tail.append(ln)
            elif s:
                self.slot_lines.append(s)

    def hits(self):
        return [(t, xy, d['dia']) for t, d in self.tools.items() for xy, _ in d['hits']]

    def write(self, path, keep_tools, note):
        """Write with only keep_tools ({tool: [hit lines]}); note goes in as a comment after the first header line."""
        out = [self.pre[0], '; ' + note] + self.pre[1:]
        for t, d in self.tools.items():
            if keep_tools.get(t):
                out += d['lines']
        out += self.post_tools + ['%'] + self.body_pre
        for t in self.tools:
            if keep_tools.get(t):
                out.append('T%d' % t)
                out += keep_tools[t]
        out += self.tail or ['M30']
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(self.eol.join(out) + self.eol)


def board_vias_text(text):
    """Top-level vias from the .kicad_pcb text: (x, y, drill, filled, capped, header). Defaults from (setup ...)."""
    setup = re.search(r'\n\t\(setup\n(.*?)\n\t\)\n', text, re.S)
    sdef = setup.group(1) if setup else ''
    dfill = bool(re.search(r'^\t\t\(filling yes\)', sdef, re.M))
    dcap = bool(re.search(r'^\t\t\(capping yes\)', sdef, re.M))
    vias = []
    for m in re.finditer(r'\n\t\(via([^\n]*)\n(.*?)\n\t\)', text, re.S):
        body = m.group(2)
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', body)
        dr = re.search(r'\(drill ([\d.]+)\)', body)
        fi = re.search(r'^\t\t\(filling (yes|no)\)', body, re.M)
        ca = re.search(r'^\t\t\(capping (yes|no)\)', body, re.M)
        lay = re.search(r'\(layers ([^)]*)\)', body)
        vias.append({'x': float(at.group(1)), 'y': float(at.group(2)), 'drill': float(dr.group(1)),
                     'filled': (fi.group(1) == 'yes') if fi else dfill, 'capped': (ca.group(1) == 'yes') if ca else dcap,
                     'kind': m.group(1).strip(), 'layers': lay.group(1) if lay else ''})
    return vias


# --------------------------------------------------------------------------------------------- the run
class Ctx:
    def __init__(self, a):
        self.a = a
        self.steps = []        # (name, status, detail)
        self.checks = []       # dict(name, level, ok, detail)
        self.warnings = []
        self.commands = []
        self.counts = collections.OrderedDict()
        self.outputs = []      # absolute paths written
        self.notes = []

    def check(self, name, ok, detail='', level='error'):
        self.checks.append({'name': name, 'level': level, 'ok': bool(ok), 'detail': detail})
        return ok

    def short(self, s):
        """s with this machine's paths replaced by tags (<work>, <out>, <repo>, <main-checkout>, kicad-cli, ...), so
        the manifest and the printed commands are portable; separators after a tag become '/'."""
        s = str(s)
        ibom = os.path.abspath(self.a.ibom_pkg) if getattr(self.a, 'ibom_pkg', None) else None
        pairs = ((getattr(self, 'work', None), '<work>'), (getattr(self, 'out', None), '<out>'),
                 (os.path.abspath(__file__), '<export_fab.py>'), (ibom, '<ibom-pkg>'),
                 (getattr(self, 'top', None), '<repo>'), (getattr(self, 'main_checkout', None), '<main-checkout>'),
                 (getattr(self, 'cli', None), 'kicad-cli'), (getattr(self, 'kpy', None), 'kicad-python'))
        # one tag per path: when two share a path (the repo IS the main checkout) the first in pairs wins, <repo>,
        # so the manifest does not depend on set order
        variants = collections.OrderedDict()
        for base, tag in pairs:
            for v in ((base, base.replace('\\', '/'), base.replace('/', '\\')) if base else ()):
                variants.setdefault(v, tag)
        for base, tag in sorted(variants.items(), key=lambda t: -len(t[0])):   # longest first (stable): the repo
            s = s.replace(base, tag)                                             # can be inside the main checkout
        return re.sub(r'(<[a-z_.-]+>)([^\s;,()\'"]*)', lambda m: m.group(1) + m.group(2).replace('\\', '/'), s)

    def portable(self, obj):
        if isinstance(obj, str):
            return self.short(obj)
        if isinstance(obj, dict):
            return collections.OrderedDict((k, self.portable(v)) for k, v in obj.items())
        if isinstance(obj, (list, tuple)):
            return [self.portable(v) for v in obj]
        return obj

    def run(self, argv, cwd=None, record=True, ok_codes=(0,)):
        if record:
            self.commands.append(' '.join(_q(self.short(x)) for x in argv))
        r = subprocess.run(argv, cwd=cwd, env=self.env, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', stdin=subprocess.DEVNULL)
        if r.returncode not in ok_codes:
            raise StepError('exit %d: %s\n%s\n%s' % (r.returncode, self.short(' '.join(argv)), r.stdout[-3000:],
                                                       r.stderr[-3000:]))
        return r.stdout + r.stderr

    def kcli(self, *args, **kw):
        return self.run([self.cli] + list(args), **kw)

    def put(self, path):
        self.outputs.append(path)
        return path


def _q(s):
    return '"%s"' % s if (' ' in s or '(' in s or s == '') else s


def step_project(C):
    s = C.s
    libdir = s.library_dir
    C.proj_root = os.path.join(C.work, 'proj')
    info = kproject.build(C.proj_root, C.repo, rev=C.sha, project_dir=s.project_dir, library='auto',
                          library_dir=libdir, library_paths=s.library_paths, require_dru=s.require_dru)
    C.project_dir = info['project_dir']
    lib = info['library']
    if libdir and 'not available' in lib:
        lib_sha = kproject.gitlink(C.repo, C.sha, kproject.under(C.project_dir, libdir))
        common = kproject.git(C.repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
        main_co = os.path.dirname(os.path.abspath(common))
        if not kproject.same_dir(main_co, C.top):
            lib = kproject.add_library(main_co, C.project_dir, lib_sha, C.proj_root, 'auto', libdir, s.library_paths)
    C.proj = os.path.dirname(info['board'])
    C.board, C.pname = info['board'], info['name']
    C.sch = os.path.join(C.proj, C.pname + '.kicad_sch')
    C.sheets = info['sheets']
    C.library_status = lib
    C.models_ok = False
    if not libdir:
        C.models_status = 'no library 3-D models (no library folder configured)'
        return '%s; %d sheets; %s; %s' % (info['source'], len(info['sheets']), lib, C.models_status)
    try:
        # library_models() also drops every model flat into the folder it is given (for footprints that name a bare
        # file). Here it fills a staging folder; only the <library-dir> tree goes into the project, and a flat copy
        # is added in step_step only for a part that would otherwise have no model. Otherwise a footprint listing
        # both 'X.stp' and '${KIPRJMOD}/<library-dir>/<models>/X.stp' gets two coincident bodies, which the repo
        # checkout (no flat files in the project folder) never shows.
        C.models_staging = os.path.join(C.work, 'models_staging')
        st = models3d.library_models(C.top, C.sha, False, C.models_staging, C.project_dir, libdir,
                                     s.library_model_paths)
        shutil.copytree(os.path.join(C.models_staging, *libdir.split('/')), os.path.join(C.proj, *libdir.split('/')),
                        dirs_exist_ok=True)
        C.models_status = st + ' (library tree only)'
        C.models_ok = True
    except models3d.ModelLibraryError as e:
        C.models_status = 'library 3-D models NOT added: %s' % e
    return '%s; %d sheets; %s; %s' % (info['source'], len(info['sheets']), lib, C.models_status)


def step_board_facts(C):
    t = read_text(C.board).replace('\r\n', '\n')   # git archive applies core.autocrlf: the copy can be CRLF
    C.board_text = t
    pp = re.search(r'\(pcbplotparams\n(.*?)\n\t\t\)', t, re.S)
    if not pp:
        raise StepError('no (pcbplotparams) in the board')
    C.plot_params = dict(re.findall(r'^\t\t\t\((\w+) ("[^"]*"|[^()\s]+)\)$', pp.group(1), re.M))
    C.props = dict(re.findall(r'^\t\(property "([^"]+)" "([^"]*)"\)', t, re.M))
    C.revision = C.props.get('REVISION', '')
    C.prefix = C.a.name or config.format_name(C.s.name_template, C.pname, C.revision)
    if not C.prefix or not re.match(r'^[A-Za-z0-9_.-]+$', C.prefix):
        raise StepError('no usable NAME (board property REVISION=%r); pass --name' % C.revision)
    C.upload_base = upload_base(C.prefix)
    lay = re.search(r'\n\t\(layers\n(.*?)\n\t\)', t, re.S)
    C.layers = [(int(n), canon, kind, user) for n, canon, kind, user in
                re.findall(r'^\t\t\((\d+) "([^"]+)" (\w+)(?: "([^"]*)")?\)', lay.group(1), re.M)]
    cu = [l for l in C.layers if l[1].endswith('.Cu')]
    order = lambda l: (0, 0) if l[1] == 'F.Cu' else ((2, 0) if l[1] == 'B.Cu' else (1, int(l[1][2:-3])))  # noqa: E731
    C.copper = sorted(cu, key=order)
    C.text_vias = board_vias_text(t)
    return 'NAME %s, REVISION %s, RELEASE_DATE %s, %d copper layers, %d vias (%d filled+capped)' % (
        C.prefix, C.revision, C.props.get('RELEASE_DATE'), len(C.copper), len(C.text_vias),
        sum(1 for v in C.text_vias if v['filled'] and v['capped']))


def step_pcbnew(C):
    out = os.path.join(C.work, 'pcbnew_dump.json')
    C.run([C.kpy, '-I', os.path.abspath(__file__), '--pcbnew-dump', C.board, out])
    with open(out, encoding='utf-8') as f:
        C.pcb = json.load(f)
    # pcbnew's shape bounding boxes can be 1 nm off the outline (e.g. 102.300001 where the Edge.Cuts Gerber reads
    # 102.300000), and 1 nm is enough to flip the last printed digit of an XYRS coordinate (x.685 printed as x.68).
    # Round the corner to 0.1 um: far below any outline grid, far above the bbox error.
    x0, y0, x1, y1 = [round(v, 4) for v in C.pcb['edge_centreline_mm']]
    C.pcb['edge_centreline_mm'] = [x0, y0, x1, y1]
    C.origin = (x0, y1)
    C.size_mil = ((x1 - x0) / MIL, (y1 - y0) / MIL)
    C.fp = collections.OrderedDict()
    C.logos = []
    dup = []
    for fp in C.pcb['footprints']:
        if fp['n_pads'] == 0 and (fp['board_only'] or '*' in fp['ref']):
            C.logos.append(fp['ref'])
            continue
        if fp['ref'] in C.fp:
            dup.append(fp['ref'])
        C.fp[fp['ref']] = fp
    C.check('board: unique references on footprints with pads', not dup, ' '.join(dup))
    return 'edge centre line x %.4f..%.4f y %.4f..%.4f mm (%.2f x %.2f mil); %d footprints, %d vias' % (
        x0, x1, y0, y1, C.size_mil[0], C.size_mil[1], len(C.pcb['footprints']), len(C.pcb['vias']))


def step_schematic(C):
    net = os.path.join(C.work, 'netlist.xml')
    C.kcli('sch', 'export', 'netlist', '--format', 'kicadxml', '-o', net, C.sch)
    root = ET.parse(net).getroot()
    C.comps = collections.OrderedDict()
    for c in root.find('components'):
        fe = c.find('fields')          # an Element's truth value is deprecated: compare with None
        fields = {f.get('name'): (f.text or '').strip() for f in (fe if fe is not None else [])}
        props = {p.get('name') for p in c.findall('property')}
        C.comps[c.get('ref')] = {'value': (c.findtext('value') or '').strip(),
                                 'footprint': (c.findtext('footprint') or '').strip(), 'fields': fields,
                                 'dnp': 'dnp' in props, 'exclude_bom': 'exclude_from_bom' in props,
                                 'exclude_board': 'exclude_from_board' in props}
    bom = os.path.join(C.work, 'bom_perref.csv')
    C.kcli('sch', 'export', 'bom', '--fields', 'Reference,Value,Footprint,MPN,Manufacturer,MANUFACTURER',
           '--labels', 'Reference,Value,Footprint,MPN,Manufacturer,MANUFACTURER', '--group-by', '',
           '--ref-range-delimiter', '', '-o', bom, C.sch)
    with open(bom, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    C.bom_refs = set()
    for r in rows:
        C.bom_refs.update(x.strip() for x in r['Reference'].split(',') if x.strip())
    return '%d schematic symbols (netlist), %d refs in the kicad-cli BOM' % (len(C.comps), len(C.bom_refs))


def step_gerbers(C):
    pp = C.plot_params
    x2_on = pp.get('usegerberattributes') != 'no'
    net_on = pp.get('usegerberadvancedattributes') != 'no'
    C.check('board plot params: X2 attributes off (usegerberattributes no)', not x2_on,
            'usegerberattributes=%s' % pp.get('usegerberattributes'), level='warn')
    C.check('board plot params: netlist attributes off (usegerberadvancedattributes no)', not net_on,
            'usegerberadvancedattributes=%s' % pp.get('usegerberadvancedattributes'), level='warn')
    C.check('board plot params: absolute origin (useauxorigin no)', pp.get('useauxorigin') == 'no',
            'useauxorigin=%s' % pp.get('useauxorigin'))
    gdir = os.path.join(C.work, 'gerber_bpp')
    os.makedirs(gdir)
    C.kcli('pcb', 'export', 'gerbers', '--board-plot-params', '-o', gdir + os.sep, C.board)
    C.forced_x1 = x2_on or net_on
    pinned = ['-l', ','.join([l[1] for l in C.copper] + ['F.Mask', 'B.Mask', 'F.Paste', 'B.Paste', 'F.Silkscreen',
                                                         'B.Silkscreen', 'Edge.Cuts']),
              '--no-x2', '--no-netlist', '--no-protel-ext', '--precision', '6']
    if pp.get('subtractmaskfromsilk') == 'yes':
        pinned.append('--subtract-soldermask')
    if pp.get('disableapertmacros') == 'yes':
        pinned.append('--disable-aperture-macros')
    xdir = os.path.join(C.work, 'gerber_pinned')
    os.makedirs(xdir)
    C.kcli('pcb', 'export', 'gerbers', *pinned, '-o', xdir + os.sep, C.board)
    src = xdir if C.forced_x1 else gdir
    if C.forced_x1:
        C.notes.append('X2/netlist attributes were ON in the board plot settings: the fab Gerbers come from the '
                       'explicit --no-x2 --no-netlist plot (X1), not from --board-plot-params')
    jdir = src
    jobs = [f for f in os.listdir(src) if f.endswith('.gbrjob')]
    if not jobs:   # creategerberjobfile no: KiCad 10.0.7 writes one anyway; fall back to the pinned plot's
        jdir = xdir
        jobs = [f for f in os.listdir(xdir) if f.endswith('.gbrjob')]
    if len(jobs) != 1:
        raise StepError('expected one gbrjob in %s, found %s' % (jdir, jobs))
    with open(os.path.join(jdir, jobs[0]), encoding='utf-8') as f:
        job = json.load(f, object_pairs_hook=collections.OrderedDict)
    sel, by_fn = [], collections.Counter()
    for fa in job['FilesAttributes']:
        fn, pol, path = fa['FileFunction'], fa.get('FilePolarity', ''), fa['Path']
        parts = fn.split(',')
        if parts[0] == 'Copper':
            n, where = int(parts[1][1:]), parts[2]
            if where not in ('Top', 'Bot', 'Inr'):
                raise StepError('unexpected copper FileFunction ' + fn)
            ext = copper_upload_ext(n, where, pol)
            canon = C.copper[n - 1][1]
            uname = C.copper[n - 1][3] or canon
            key = 'Copper'
        else:
            key = 'Profile' if parts[0] == 'Profile' else ','.join(parts[:2])
            if key not in NON_COPPER:
                continue
            canon, ext = NON_COPPER[key]
            uname = next((l[3] or l[1] for l in C.layers if l[1] == canon or l[3] == canon), canon)
        by_fn[key] += 1
        safe = fab_layer_stem(path, C.pname)
        sel.append({'kicad_file': path, 'fab_file': '%s_%s.gbr' % (C.prefix, safe), 'upload_file': '%s.%s' % (C.upload_base, ext),
                    'layer': canon, 'board_name': uname, 'function': fn, 'polarity': pol, 'fa': fa})
    ok_set = by_fn['Copper'] == len(C.copper) and all(by_fn[k] == 1 for k in NON_COPPER)
    C.check('gerbers: %d copper + 7 fab layers in the gbrjob' % len(C.copper), ok_set, dict(by_fn))
    if not ok_set:
        raise StepError('fab layer set incomplete: %s' % dict(by_fn))
    names = [s['fab_file'] for s in sel] + [s['upload_file'] for s in sel]
    if len(set(n.lower() for n in names)) != len(names):
        raise StepError('file name collision: %s' % names)
    fab = os.path.join(C.out, 'fab')
    bad_x2 = []
    for s in sel:
        srcf = os.path.join(src, s['kicad_file'])
        n = x2_attribute_lines(srcf)
        if n:
            bad_x2.append('%s:%d' % (s['kicad_file'], n))
        shutil.copyfile(srcf, C.put(os.path.join(fab, s['fab_file'])))
        s['path'] = os.path.join(fab, s['fab_file'])
    C.check('gerbers: X2 off in all %d files (no %%TF/%%TA/%%TO/%%TD lines)' % len(sel), not bad_x2, ' '.join(bad_x2))
    # pinned-flag cross-check: the board's settings must equal the flags written down here
    diff = []
    for s in sel:
        pa, pb = os.path.join(gdir, s['kicad_file']), os.path.join(xdir, s['kicad_file'])
        if not (os.path.exists(pa) and os.path.exists(pb)):   # e.g. the board plots with Protel extensions
            diff.append(s['kicad_file'] + ' (not written by both plots)')
            continue
        a_ = [l for l in read_text(pa).splitlines() if not DATE_LINE_RE.search(l)]
        b_ = [l for l in read_text(pb).splitlines() if not DATE_LINE_RE.search(l)]
        if a_ != b_:
            diff.append(s['kicad_file'])
    C.check('gerbers: --board-plot-params output identical to the pinned flags (%s)' % ' '.join(pinned[2:]),
            not diff, 'differ: ' + ', '.join(diff) if diff else '%d/%d identical except dates' % (len(sel), len(sel)),
            level='warn')
    keep = {s['kicad_file']: s for s in sel}
    job['FilesAttributes'] = [collections.OrderedDict([('Path', keep[fa['Path']]['fab_file'])] +
                                                      [(k, v) for k, v in fa.items() if k != 'Path'])
                              for fa in job['FilesAttributes'] if fa['Path'] in keep]
    jpath = C.put(os.path.join(fab, '%s_job.gbrjob' % C.prefix))
    with open(jpath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(job, indent=2) + '\n')
    C.gerbers = sel
    C.counts['gerber_files'] = len(sel)
    # outline vs pcbnew
    edge = next(s for s in sel if s['layer'] == 'Edge.Cuts')
    _, pts = gerber_ops(edge['path'])
    gx0, gx1 = min(p[0] for p in pts), max(p[0] for p in pts)
    gy0, gy1 = min(p[1] for p in pts), max(p[1] for p in pts)
    x0, y0, x1, y1 = C.pcb['edge_centreline_mm']
    d = max(abs(gx0 - x0), abs(gx1 - x1), abs(gy0 + y1), abs(gy1 + y0))
    C.outline_gerber = (gx0, gy0, gx1, gy1)
    C.check('outline: Edge.Cuts Gerber extents = pcbnew centre-line box (Y negated)', d < 0.001,
            'Gerber X %.4f..%.4f Y %.4f..%.4f, max diff %.4f mm' % (gx0, gx1, gy0, gy1, d))
    # silk strokes under MacroFab's 5 mil (0.127 mm) minimum line: counted for the DFM email, not a check
    thin = {}
    for s in sel:
        if s['layer'] not in ('F.Silkscreen', 'B.Silkscreen'):
            continue
        g = gerber_objects(s['path'])
        widths = collections.Counter()
        for x0_, y0_, x1_, y1_, dc, pol in g['draws']:
            ap = g['apertures'].get(dc)
            if pol == 'D' and ap and ap[0] == 'C' and ap[1] and ap[1][0] < 0.127 - 1e-9:
                widths['%.3f' % ap[1][0]] += 1
        thin[s['layer']] = dict(sorted(widths.items()))
    C.counts['silk_draws_under_0.127mm'] = thin
    C.notes.append('Silk strokes under 0.127 mm (MacroFab 5 mil minimum; known item for the DFM email): ' +
                   '; '.join('%s %s' % (k, ', '.join('%d x %s mm' % (n, w) for w, n in v.items()) or 'none')
                             for k, v in thin.items()))
    return '%d Gerbers from %s; gbrjob cut to them%s' % (
        len(sel), '--board-plot-params' if not C.forced_x1 else 'the pinned-flag plot (X1 forced)',
        '' if not diff else '; pinned-flag plot DIFFERS')


def step_drill(C):
    ddir = os.path.join(C.work, 'drill')
    os.makedirs(ddir)
    rpt = os.path.join(ddir, 'drill_report.rpt')
    C.kcli('pcb', 'export', 'drill', '--format', 'excellon', '--excellon-units', 'mm', '--excellon-zeros-format',
           'decimal', '--drill-origin', 'absolute', '--excellon-oval-format', 'route', '--excellon-separate-th',
           '--generate-map', '--map-format', 'pdf', '--generate-report', '--report-path', rpt, '-o', ddir + os.sep,
           C.board)
    pth_src = os.path.join(ddir, C.pname + '-PTH.drl')
    npth_src = os.path.join(ddir, C.pname + '-NPTH.drl')
    for p in (pth_src, npth_src, rpt):
        if not os.path.exists(p):
            raise StepError('kicad-cli wrote no ' + os.path.basename(p))
    pth, npth = Excellon(pth_src), Excellon(npth_src)
    C.check('drill: Excellon header has METRIC and FMAT,2', 'METRIC' in pth.pre and 'FMAT,2' in pth.pre,
            ' / '.join(pth.pre[:8]))
    slots = pth.slot_lines + npth.slot_lines
    pad_slots = [(f['ref'], s) for f in C.pcb['footprints'] for s in f['slots']]
    C.check('drill: no slots / routed holes (MacroFab wants slots on Edge.Cuts)', not slots and not pad_slots,
            '%d drill-file lines, pads %s' % (len(slots), pad_slots))
    bad_vias = [v for v in C.text_vias if v['kind'] or '"F.Cu" "B.Cu"' not in v['layers']]
    C.check('drill: every via is a through via F.Cu-B.Cu', not bad_vias, '%d others' % len(bad_vias))
    C.check('drill: pcbnew and the board text list the same number of vias',
            len(C.pcb['vias']) == len(C.text_vias), '%d vs %d' % (len(C.pcb['vias']), len(C.text_vias)))
    filled = [v for v in C.text_vias if v['filled'] or v['capped']]
    groups = collections.defaultdict(set)   # pcbnew's own view: vias grouped by (filling mode, capping mode)
    for v in C.pcb['vias']:
        groups[(v['GetFillingMode'], v['GetCappingMode'])].add((round(v['pos_mm'][0], 4), round(v['pos_mm'][1], 4)))
    want_set = {(round(v['x'], 4), round(v['y'], 4)) for v in filled}
    required = C.s.require_filled_vias
    C.check('drill: pcbnew sees the same filled vias (one filling/capping mode group = the board-text set)',
            filled_vias_seen(want_set, groups, required),
            ', '.join('%s:%d' % ('/'.join(k), len(g)) for k, g in sorted(groups.items())))
    odd = [v for v in filled if not (v['filled'] and v['capped'])]
    C.check('drill: protected vias are all filled AND capped (Type VII)', not odd,
            '; '.join('(%.3f, %.3f) filled=%s capped=%s' % (v['x'], v['y'], v['filled'], v['capped']) for v in odd))
    # move each filled via's hit out of PTH (match by coordinate and drill)
    keep = {t: [ln for _, ln in d['hits']] for t, d in pth.tools.items()}
    moved = collections.OrderedDict()
    unmatched = []
    for v in filled:
        want = (v['x'], -v['y'])
        found = [(t, i) for t, d in pth.tools.items() for i, (xy, _) in enumerate(d['hits'])
                 if abs(xy[0] - want[0]) < 0.0015 and abs(xy[1] - want[1]) < 0.0015 and abs(d['dia'] - v['drill']) < 0.0005]
        if len(found) != 1:
            unmatched.append('(%.4f, %.4f) %d matches' % (v['x'], v['y'], len(found)))
            continue
        t, i = found[0]
        ln = pth.tools[t]['hits'][i][1]
        keep[t].remove(ln)
        moved.setdefault(t, []).append(ln)
    C.check('drill: each filled via found exactly once in the PTH file', filled_vias_found(unmatched, filled, required),
            '; '.join(unmatched) or '%d of %d' % (sum(len(v) for v in moved.values()), len(filled)))
    fab = os.path.join(C.out, 'fab')
    n_before = len(pth.hits())
    names = {'pth': '%s_PTH.drl' % C.prefix, 'filled': '%s_PTH_FILLED.drl' % C.prefix, 'npth': '%s_NPTH.drl' % C.prefix}
    n_moved = sum(len(v) for v in moved.values())
    pth_out = C.put(os.path.join(fab, names['pth']))
    pth.write(pth_out, keep, '%d filled-and-capped vias moved to %s by export_fab.py' % (n_moved, names['filled']))
    fil_out = C.put(os.path.join(fab, names['filled']))
    pth.write(fil_out, moved, 'Filled and capped vias (IPC-4761 Type VII, non-conductive fill, capped): %d holes split '
                              'from %s by export_fab.py' % (n_moved, names['pth']))
    shutil.copyfile(npth_src, C.put(os.path.join(fab, names['npth'])))
    for kind in ('PTH', 'NPTH'):
        m = os.path.join(ddir, '%s-%s-drl_map.pdf' % (C.pname, kind))
        if os.path.exists(m):
            shutil.copyfile(m, C.put(os.path.join(fab, '%s_%s_drl_map.pdf' % (C.prefix, kind))))
        else:
            C.check('drill: map %s written' % kind, False, m)
    # re-read what was written
    P, F, N = Excellon(pth_out), Excellon(fil_out), Excellon(os.path.join(fab, names['npth']))
    counts = {'pth': len(P.hits()), 'filled': len(F.hits()), 'npth': len(N.hits())}
    C.check('drill: PTH + filled = KiCad PTH (%d + %d = %d)' % (counts['pth'], counts['filled'], n_before),
            counts['pth'] + counts['filled'] == n_before and counts['filled'] == len(filled))
    C.counts.update({'drill_' + k: v for k, v in counts.items()})
    C.counts['drill_tools'] = {
        'pth': ['%.3f x%d' % (d['dia'], len(d['hits'])) for d in P.tools.values() if d['hits']],
        'filled': ['%.3f x%d' % (d['dia'], len(d['hits'])) for d in F.tools.values() if d['hits']],
        'npth': ['%.3f x%d' % (d['dia'], len(d['hits'])) for d in N.tools.values() if d['hits']]}
    C.filled_vias = [{'x_mm': v['x'], 'y_mm': v['y'], 'drill_mm': v['drill']} for v in filled]
    with open(rpt, encoding='utf-8') as f:
        rep = f.read()
    rep += '\n\nFilled-via split (%s):\n' % C.generator
    rep += ('    %d holes (vias with (filling yes) (capping yes) in the board, drill %s mm) moved from %s-PTH.drl to %s\n'
            '    (IPC-4761 Type VII: non-conductive epoxy fill, capped). %s keeps %d plated holes; %s has %d.\n'
            '    The tables above and the drill maps are KiCad\'s, before the split (%d plated holes).\n'
            '    Renamed: %s-PTH.drl -> %s, %s-NPTH.drl -> %s.\n') % (
        n_moved, '/'.join(sorted({'%.3f' % v['drill'] for v in filled})), C.pname, names['filled'], names['pth'],
        counts['pth'], names['npth'], counts['npth'], n_before, C.pname, names['pth'], C.pname, names['npth'])
    rep += '\nFinal drill files (read back from the three files written; tool, finished diameter mm, hits):\n'
    for key, ex in (('pth', P), ('filled', F), ('npth', N)):
        used = [(t, d) for t, d in ex.tools.items() if d['hits']]
        rep += '    %s: %d holes\n' % (names[key], len(ex.hits()))
        rep += ''.join('        T%d  %.3f  x%d\n' % (t, d['dia'], len(d['hits'])) for t, d in used)
    with open(C.put(os.path.join(fab, '%s_drill_report.txt' % C.prefix)), 'w', encoding='utf-8', newline='\n') as f:
        f.write(rep)
    # origin / line-up: every hit inside the outline and on a copper flash on both outer layers
    gx0, gy0, gx1, gy1 = C.outline_gerber
    allhits = [(xy, k) for k, ex in (('pth', P), ('filled', F), ('npth', N)) for _, xy, _ in ex.hits()]
    outside = [xy for xy, _ in allhits if not (gx0 <= xy[0] <= gx1 and gy0 <= xy[1] <= gy1)]
    C.check('drill: all %d hits inside the outline (same absolute frame as the Gerbers)' % len(allhits), not outside,
            '%d outside' % len(outside))
    detail = []
    for lay in (C.copper[0][1], C.copper[-1][1]):
        g = next(s for s in C.gerbers if s['layer'] == lay)
        fl, _ = gerber_ops(g['path'])
        grid = set((round(x * 1000), round(y * 1000)) for x, y in fl)

        def on_flash(xy):
            kx, ky = round(xy[0] * 1000), round(xy[1] * 1000)
            return any((kx + i, ky + j) in grid for i in (-1, 0, 1) for j in (-1, 0, 1))
        plated = [(xy, k) for xy, k in allhits if k != 'npth']
        miss = [xy for xy, k in plated if not on_flash(xy)]
        miss_f = [xy for xy, k in plated if k == 'filled' and not on_flash(xy)]
        detail.append('%s: %d/%d plated hits on a flash%s' % (g['board_name'], len(plated) - len(miss), len(plated),
                                                             (' (filled missing %d)' % len(miss_f)) if miss_f else ''))
        C.check('drill/Gerber line-up on %s: every plated hit sits on a copper flash' % g['board_name'],
                not miss, detail[-1] + ('; first misses %s' % miss[:4] if miss else ''))
    return 'PTH %d + FILLED %d (from %d), NPTH %d; %s' % (counts['pth'], counts['filled'], n_before, counts['npth'],
                                                         '; '.join(detail))


def step_placement(C):
    x0, y1 = C.origin
    W, H = C.size_mil
    rows, omitted, errs, warns = [], [], [], []
    for ref in C.comps:
        c = C.comps[ref]
        if ref not in C.fp:
            if c['exclude_board']:
                omitted.append(ref + ' (not on board)')
                continue
            errs.append('%s in the schematic but not on the board' % ref)
    for ref, fp in C.fp.items():
        if ref not in C.comps:
            if fp['board_only'] or fp['n_pads'] == 0:
                omitted.append(ref + ' (board only)')
            else:
                errs.append('%s on the board but not in the schematic' % ref)
            continue
        c = C.comps[ref]
        mpn = c['fields'].get('MPN', '').strip()
        if c['exclude_bom'] and not mpn and is_non_part(ref, c['footprint'], C.non_part_refs, C.non_part_libs):
            omitted.append(ref)
            continue
        pop = 0 if (c['dnp'] or c['exclude_bom']) else 1
        if fp['dnp'] != c['dnp']:
            errs.append('%s DNP: board %s, schematic %s' % (ref, fp['dnp'], c['dnp']))
        if fp['exclude_bom'] != c['exclude_bom']:
            errs.append('%s exclude-from-BOM: board %s, schematic %s' % (ref, fp['exclude_bom'], c['exclude_bom']))
        if fp['value'] != c['value']:
            errs.append('%s value: board %r, schematic %r' % (ref, fp['value'], c['value']))
        fpname = fp['fpid'].split(':', 1)[-1]
        if c['footprint'].split(':', 1)[-1] != fpname:
            errs.append('%s footprint: board %s, schematic %s' % (ref, fp['fpid'], c['footprint']))
        if fp['mpn'] is not None and fp['mpn'].strip() != mpn:
            errs.append('%s MPN: board %r, schematic %r' % (ref, fp['mpn'], mpn))
        if pop and not mpn:
            errs.append('%s fitted with no MPN' % ref)
        for label, s in (('value', fp['value']), ('footprint', fpname), ('MPN', mpn)):
            if any(ord(ch) > 126 or ord(ch) < 32 for ch in s):
                errs.append('%s %s %r is not printable ASCII' % (ref, label, s))
        if pop and (DNP_WORD_RE.search(fp['value']) or DNP_WORD_RE.search(mpn)):
            warns.append('%s Populate 1 but Value/MPN %r contains DNP/DNM' % (ref, mpn or fp['value']))
        if fp['pad_box_mm']:
            l, t, r, b = fp['pad_box_mm']
            cx, cy = (l + r) / 2, (t + b) / 2
            sx = (fp['pad_extent_local_mm'][1] - fp['pad_extent_local_mm'][0]) / MIL
            sy = (fp['pad_extent_local_mm'][3] - fp['pad_extent_local_mm'][2]) / MIL
        else:
            cx, cy = fp['pos_mm']
            sx = sy = 0.0
            warns.append('%s has no pads: footprint origin used' % ref)
        X, Y = xyrs_point(cx, cy, C.origin)
        side = 2 if fp['side'] == 'B' else 1
        raw, rot = xyrs_rotation(fp['orientation'], side)
        if abs(raw - round(raw)) > 0.01:
            warns.append('%s rotation %.3f rounded to %d' % (ref, raw, rot))
        p1, crt = fp.get('pad1_mm'), fp.get('courtyard_box_mm')
        rows.append({'ref': ref, 'x': X, 'y': Y, 'rot': rot, 'side': side, 'type': 2 if fp['kind'] == 'TH' else 1,
                     'sx': sx, 'sy': sy, 'value': fp['value'], 'footprint': fpname, 'pop': pop, 'mpn': mpn,
                     'kicad_rot': fp['orientation'], 'kind': fp['kind'],
                     # pad 1 relative to the XYRS point, mil, top view (X right, Y up)
                     'pin1': [round((p1[0] - cx) / MIL, 2), round((cy - p1[1]) / MIL, 2)] if p1 else None,
                     'pin1_mm': [round(p1[0], 4), round(-p1[1], 4)] if p1 else None,     # Gerber frame
                     # courtyard-box centre (the body, roughly) in XYRS mil
                     'body': [round(((crt[0] + crt[2]) / 2 - x0) / MIL, 2), round((y1 - (crt[1] + crt[3]) / 2) / MIL, 2)]
                     if crt else None})
    rows.sort(key=lambda r: natural_key(r['ref']))
    omitted.sort(key=natural_key)
    neg =['%s (%.2f, %.2f)' % (r['ref'], r['x'], r['y']) for r in rows
           if not (-0.005 <= r['x'] <= W + 0.005 and -0.005 <= r['y'] <= H + 0.005)]
    C.check('XYRS: every row inside 0..%.2f x 0..%.2f mil (no negatives)' % (W, H), not neg, ', '.join(neg[:10]))
    C.check('XYRS: board and schematic agree (DNP, BOM exclusion, value, footprint, MPN; MPN on fitted parts; ASCII)',
            not errs, '; '.join(errs[:20]))
    pop1 = {r['ref'] for r in rows if r['pop']}
    C.check('XYRS: Populate 1 set = the kicad-cli BOM refs (%d)' % len(C.bom_refs), pop1 == C.bom_refs,
            'only XYRS: %s; only BOM: %s' % (sorted(pop1 - C.bom_refs, key=natural_key),
                                             sorted(C.bom_refs - pop1, key=natural_key)))
    for w in warns:
        C.check('XYRS: ' + w, False, level='warn')
    fid = [(ref, C.fp[ref]) for ref in sorted(C.fp, key=natural_key) if is_fiducial(ref, C.fp[ref]['fpid'])]
    C.fiducials = []
    for ref, fp in fid:
        l, t, r, b = fp['pad_box_mm'] or (fp['pos_mm'] * 2)
        C.fiducials.append({'ref': ref, 'side': 'bottom' if fp['side'] == 'B' else 'top',
                            'x_mil': round(((l + r) / 2 - x0) / MIL, 2), 'y_mil': round((y1 - (t + b) / 2) / MIL, 2),
                            'kicad_mm': [round((l + r) / 2, 4), round((t + b) / 2, 4)]})
    n1 = len(pop1)
    head = [
        '# MacroFab XYRS placement file: %s %s' % (C.props.get('BOARD_NAME', C.pname), C.revision),
        '# Source: %s ecad commit %s (%s), %s, %s' % (
            C.pname, C.sha, C.subject if len(C.subject) <= 72 else C.subject[:69] + '...', C.kicad_version,
            C.generator),
        '# Units mil. Origin = bottom-left corner of the board outline (Edge.Cuts centre line) = KiCad (%.4f, %.4f) mm;'
        ' X right, Y up; bottom-side X not mirrored. Board %.2f x %.2f mil.' % (x0, y1, W, H),
        '# Position = centre of the pad bounding box. Rotation: top = KiCad orientation; bottom = KiCad orientation'
        ' + 180 (mod 360).',
        '# Side 1 = top (F.Cu), 2 = bottom (B.Cu). Type 1 = SMT, 2 = PTH (KiCad through-hole attribute). X/Y-Size ='
        ' pad extents in the footprint frame.',
        '# %d rows: %d Populate 1, %d Populate 0 (DNP or not a purchased part). Not listed: %s.' % (
            len(rows), n1, len(rows) - n1, ', '.join(omitted + (['%d board-only logo footprint%s (%s)' % (
                len(C.logos), 's' if len(C.logos) != 1 else '', ', '.join(sorted(set(C.logos))))] if C.logos else []))
            or 'none'),
        '# Fiducials (not rows): ' + ('; '.join('%s %s %.2f %.2f' % (f['ref'], f['side'], f['x_mil'], f['y_mil'])
                                                for f in C.fiducials) or 'none'),
        '#Designator\tX-Loc\tY-Loc\tRotation\tSide\tType\tX-Size\tY-Size\tValue\tFootprint\tPopulate\tMPN',
    ]
    head = [h.encode('ascii', 'replace').decode('ascii') for h in head]
    lines = head + ['\t'.join([r['ref'], '%.2f' % r['x'], '%.2f' % r['y'], '%d' % r['rot'], str(r['side']),
                               str(r['type']), '%.2f' % r['sx'], '%.2f' % r['sy'], r['value'], r['footprint'],
                               str(r['pop']), r['mpn']]) for r in rows]
    xyrs = C.put(os.path.join(C.out, 'assembly', '%s.XYRS' % C.prefix))
    # a non-ASCII value is already an error above; write it as '?' so the rest of the package is still produced
    with open(xyrs, 'w', encoding='ascii', errors='replace', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    with open(xyrs, encoding='ascii') as f:
        back = [l.rstrip('\n').split('\t') for l in f if not l.startswith('#')]
    C.check('XYRS: %d data rows, 12 tab fields each' % len(rows), len(back) == len(rows) and all(len(r) == 12 for r in back))
    C.xyrs_rows = rows
    C.xyrs_path = xyrs
    C.omitted = omitted
    C.counts.update({'xyrs_rows': len(rows), 'fitted': n1, 'pop0': len(rows) - n1,
                     'fitted_top': sum(1 for r in rows if r['pop'] and r['side'] == 1),
                     'fitted_bottom': sum(1 for r in rows if r['pop'] and r['side'] == 2),
                     'rows_top': sum(1 for r in rows if r['side'] == 1), 'rows_bottom': sum(1 for r in rows if r['side'] == 2),
                     'pth_parts': sorted((r['ref'] for r in rows if r['type'] == 2), key=natural_key),
                     'populate0': sorted((r['ref'] for r in rows if not r['pop']), key=natural_key)})
    # KiCad position file (reference; MacroFab does not read it)
    pos = C.put(os.path.join(C.out, 'assembly', '%s_pos.csv' % C.prefix))
    C.kcli('pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'both', '--exclude-dnp', '-o', pos,
           C.board)
    C.notes.append('KiCad pos.csv: --exclude-dnp (a pos file has no Populate column, so DNP parts are left out); it '
                   'keeps %s; Gerber frame (Y negative); raw KiCad rotation. Reference only: MacroFab reads the '
                   'XYRS.' % C.s.pos_note_keeps)
    with open(pos, encoding='utf-8-sig', newline='') as f:
        prow = list(csv.DictReader(f))
    want = collections.Counter(fp['ref'] for fp in C.pcb['footprints'] if not fp['exclude_pos'] and not fp['dnp'])
    got = collections.Counter(r['Ref'] for r in prow)
    C.check('pos: rows = footprints not excluded from pos files and not DNP (%d)' % sum(want.values()), got == want,
            'extra %s missing %s' % (sorted((got - want).elements()), sorted((want - got).elements())))
    byref = {fp['ref']: fp for fp in C.pcb['footprints']}
    off = [r['Ref'] for r in prow if r['Ref'] in byref and (
        abs(float(r['PosX']) - byref[r['Ref']]['pos_mm'][0]) > 0.001 or abs(float(r['PosY']) + byref[r['Ref']]['pos_mm'][1]) > 0.001)]
    C.check('pos: absolute frame = Gerber frame (PosX = x, PosY = -y of the footprint origin)', not off, ' '.join(off[:10]))
    C.counts['pos_rows'] = len(prow)
    # independent cross-check of the XYRS transform against KiCad's own file, on parts whose origin is the pad centre
    xr = {r['ref']: r for r in rows}
    n = 0
    dev = 0.0
    rot_bad, offset = [], []
    for pr in prow:
        r, fp = xr.get(pr['Ref']), byref.get(pr['Ref'])
        if not r or not fp or not fp['pad_box_mm']:
            continue
        l, t, rr, b = fp['pad_box_mm']
        d = math.hypot((l + rr) / 2 - fp['pos_mm'][0], (t + b) / 2 - fp['pos_mm'][1])
        if d > 0.05:
            offset.append('%s %.2f mm' % (pr['Ref'], d))
        want = (float(pr['Rot']) + (180 if pr['Side'] == 'bottom' else 0)) % 360
        if min(abs(want - r['rot']), 360 - abs(want - r['rot'])) > 0.5:
            rot_bad.append('%s pos %s %s -> XYRS %d' % (pr['Ref'], pr['Rot'], pr['Side'], r['rot']))
        if d > 0.001:
            continue
        n += 1
        dev = max(dev, abs((float(pr['PosX']) - x0) / MIL - r['x']), abs((y1 + float(pr['PosY'])) / MIL - r['y']))
    C.check('XYRS vs KiCad pos: same frame on the %s whose origin is the pad centre (max diff %.3f mil)'
            % (plural(n, 'part'), dev), n > 0 and dev < 0.05)
    shared = len([p for p in prow if p['Ref'] in xr])
    C.check('XYRS vs KiCad pos: rotation = pos Rot (top) / pos Rot + 180 (bottom) on %s %s'
            % ('the' if shared == 1 else 'all', plural(shared, 'shared part')), not rot_bad, '; '.join(rot_bad[:10]))
    C.notes.append('XYRS position is the pad-box centre; footprints whose origin is > 0.05 mm away from it: ' +
                   ', '.join(offset))
    # placement-review data: pad 1 per row, and rows whose courtyard (body) centre is away from the XYRS point
    C.pin1 = collections.OrderedDict((r['ref'], {'xyrs_rot': r['rot'], 'side': r['side'], 'pad1_offset_mil': r['pin1'],
                                                 'pad1_gerber_mm': r['pin1_mm']}) for r in rows if r['pin1'])
    C.body_offsets = collections.OrderedDict()
    for r in rows:
        if r['body']:
            d_mm = math.hypot(r['body'][0] - r['x'], r['body'][1] - r['y']) * MIL
            if d_mm > 0.25:
                C.body_offsets[r['ref']] = {'xyrs_mil': [round(r['x'], 2), round(r['y'], 2)],
                                            'courtyard_centre_mil': r['body'], 'offset_mm': round(d_mm, 3),
                                            'populate': r['pop']}
    C.notes.append('XYRS point vs courtyard-box (body) centre, parts more than 0.25 mm apart (the XYRS keeps the '
                   'pad-pattern centre, as MacroFab\'s generator does): ' + '; '.join(
                       '%s %s -> body %s mil (%.2f mm)' % (k, v['xyrs_mil'], v['courtyard_centre_mil'], v['offset_mm'])
                       for k, v in C.body_offsets.items()))
    return 'XYRS %d rows (%d Populate 1: %d top / %d bottom; %d Populate 0); omitted %s; pos.csv %d rows' % (
        len(rows), n1, C.counts['fitted_top'], C.counts['fitted_bottom'], len(rows) - n1, ' '.join(omitted), len(prow))


def paste_findings(footprints, rows, paste, eps=0.005):
    """Paste on parts that are not placed, and fitted SMT parts with no paste.

    footprints: {ref: pcbnew_dump record}; rows: the XYRS rows; paste: {'F': gerber_objects(F.Paste),
    'B': gerber_objects(B.Paste)}. A paste object belongs to a part when its bounding box (a flash: its centre) lies
    more than eps inside the part's pad box, on the part's own side. Returns
      source   {ref: [str]}      paste in the board on a Populate 0 part: pads on a paste layer, footprint graphics on
                                 F/B.Paste (named by uuid; a filled fp_poly exposed-pad window is the usual one),
      plotted  {ref: Counter}    plotted paste objects inside a Populate 0 part's pad box, by kind,
      unpasted [ref]             fitted SMT (Type 1) rows with no paste object in their pad box."""
    def boxes(g):
        out = [('flash', x, y, x, y) for x, y, _, pol in g['flashes'] if pol == 'D']
        for pts, pol in g['regions']:
            if pol == 'D':
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                out.append(('region', min(xs), min(ys), max(xs), max(ys)))
        out += [('draw', min(a, c), min(b, d), max(a, c), max(b, d)) for a, b, c, d, _, pol in g['draws'] if pol == 'D']
        return out
    objs = {s: boxes(g) for s, g in paste.items()}

    def inside(o, box):          # box: KiCad (left, top, right, bottom), Y down; objects: Gerber frame, Y up
        l, t, r, b = box
        return o[1] < r - eps and o[3] > l + eps and o[2] < -t - eps and o[4] > -b + eps

    source, plotted, unpasted = collections.OrderedDict(), collections.OrderedDict(), []
    for row in rows:
        fp = footprints.get(row['ref'])
        if not fp or not fp.get('pad_box_mm'):
            continue
        side = 'F' if row['side'] == 1 else 'B'
        hits = [o for o in objs.get(side, []) if inside(o, fp['pad_box_mm'])]
        if not row['pop']:
            src = []
            if fp.get('paste_pads'):
                src.append('%d pad%s on a paste layer (%s)' % (
                    len(fp['paste_pads']), 's' if len(fp['paste_pads']) != 1 else '',
                    ', '.join('%s %s' % (p[0], '+'.join(p[1:])) for p in fp['paste_pads'][:6])))
            for g in fp.get('paste_graphics') or []:
                bb = g['bbox_mm']
                src.append('%s on %s, uuid %s, %.2f x %.2f mm at (%.3f, %.3f)' % (
                    g['class'], g['layer'], g['uuid'], bb[2] - bb[0], bb[3] - bb[1], (bb[0] + bb[2]) / 2,
                    (bb[1] + bb[3]) / 2))
            if src:
                source[row['ref']] = src
            if hits:
                plotted[row['ref']] = collections.Counter(o[0] for o in hits)
        elif row['type'] == 1 and not hits:
            unpasted.append(row['ref'])
    return source, plotted, unpasted


def step_paste(C):
    paste = {}
    for side, layer in (('F', 'F.Paste'), ('B', 'B.Paste')):
        g = next(s for s in C.gerbers if s['layer'] == layer)
        paste[side] = gerber_objects(g['path'])
        C.counts['paste_' + side] = {k: len(paste[side][k]) for k in ('flashes', 'regions', 'draws')}
    source, plotted, unpasted = paste_findings(C.fp, C.xyrs_rows, paste)
    accept = {r.strip() for r in (C.a.accept_dnp_paste or '').split(',') if r.strip()}
    pop0 = [r['ref'] for r in C.xyrs_rows if not r['pop']]

    def detail(d, fmt):
        return '; '.join('%s: %s' % (r, fmt(v)) for r, v in d.items())
    src_bad = collections.OrderedDict((r, v) for r, v in source.items() if r not in accept)
    plot_bad = collections.OrderedDict((r, v) for r, v in plotted.items() if r not in accept)
    C.check('paste: no paste in the board on the %s (no pad on F/B.Paste, no footprint graphic on F/B.Paste)'
            % plural(len(pop0), 'Populate 0 part'), not src_bad, detail(src_bad, lambda v: ' | '.join(v)))
    C.check('paste: no paste flash, region or draw inside a Populate 0 part\'s pad box (its own side)', not plot_bad,
            detail(plot_bad, lambda v: ', '.join('%d %s' % (n, k) for k, n in sorted(v.items()))))
    for r in sorted(accept, key=natural_key):
        if r in source or r in plotted:
            C.check('paste: %s carries paste, accepted by --accept-dnp-paste: the order notes must say "no paste at %s"'
                    % (r, r), False, ' | '.join(source.get(r, [])) + ('; plotted: %s' % dict(plotted[r])
                                                                         if r in plotted else ''), level='warn')
            C.notes.append('--accept-dnp-paste %s: the paste Gerbers still print paste at %s; tell MacroFab "no paste '
                           'at %s (DNP)"' % (r, r, r))
        else:
            C.check('paste: %s is in --accept-dnp-paste but carries no paste: drop it from the list' % r, False,
                    level='warn')
    C.check('paste: every fitted SMT (Type 1) row has paste in its pad box (control: the check above sees paste)',
            not unpasted, ' '.join(unpasted), level='warn')
    bp = C.pcb.get('board_paste_graphics') or []
    C.check('paste: no board-level (non-footprint) graphics on F/B.Paste', not bp,
            '; '.join('%s %s %s' % (g['class'], g['layer'], g['uuid']) for g in bp), level='warn')
    C.paste = {'populate0_checked': len(pop0), 'board_sources': source,
               'plotted_inside_pad_box': {r: dict(v) for r, v in plotted.items()},
               'accepted': sorted(accept, key=natural_key), 'fitted_smt_without_paste': unpasted,
               'gerber_objects': {s: C.counts['paste_' + s] for s in ('F', 'B')}}
    return 'F.Paste %s, B.Paste %s; %s: %s' % (
        C.counts['paste_F'], C.counts['paste_B'], plural(len(pop0), 'Populate 0 part'),
        'no paste' if not source and not plotted else 'PASTE on ' + ', '.join(
            sorted(set(source) | set(plotted), key=natural_key)))


def step_sch_pdf(C):
    out = C.put(os.path.join(C.out, 'docs', '%s_schematic.pdf' % C.prefix))
    C.kcli('sch', 'export', 'pdf', '--theme', '_builtin_default', '-o', out, C.sch)
    n = page_count(out)
    C.counts['schematic_pages'] = n
    C.check('schematic PDF: %s >= %s' % (plural(n, 'page'), plural(len(C.sheets), 'hierarchy sheet')),
            n >= len(C.sheets))
    return plural(n, 'page')


def step_assembly_pdf(C):
    common = ['--mode-single', '--include-border-title', '--black-and-white', '--sketch-DNP-footprints-on-fab-layers',
              '--crossout-DNP-footprints-on-fab-layers', '--drill-shape-opt', '0', '--scale', '1', '--theme',
              '_builtin_default']
    pages = []
    # DOC_TYPE feeds the drawing sheet's "${BOARD_NAME} ${DOC_TYPE} Document" title and the Sheet Title cell (~28
    # characters wide); the title-block comments cannot be set from the command line
    for side, layer, extra, title in (('top', 'F.Fab', [], 'Top Assembly'),
                                      ('bottom', 'B.Fab', ['--mirror'], 'Bottom Assembly')):
        p = os.path.join(C.work, 'assembly_%s.pdf' % side)
        C.kcli('pcb', 'export', 'pdf', '-l', '%s,Edge.Cuts' % layer, *common, *extra, '-D', 'DOC_TYPE=' + title,
               '-o', p, C.board)
        pages.append(p)
    out = os.path.join(C.out, 'assembly', '%s_assembly.pdf' % C.prefix)
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        PdfReader = PdfWriter = None
    if PdfWriter is None:
        # no merge: one file per side, each a one-page PDF; the designator check below still runs on them
        sheets = []
        for (side, p), xyrs_side in zip(zip(('top', 'bottom'), pages), (1, 2)):
            dst = C.put(os.path.join(C.out, 'assembly', '%s_assembly_%s.pdf' % (C.prefix, side)))
            shutil.copyfile(p, dst)
            sheets.append((dst, 0, xyrs_side))
        C.check('assembly PDF: pypdf missing, written as two files', False, level='warn')
        summary = 'two files (no pypdf)'
    else:
        w = PdfWriter()
        for p in pages:
            for pg in PdfReader(p).pages:
                w.add_page(pg)
        w.add_metadata({'/Title': '%s %s assembly drawing (top F.Fab, bottom B.Fab mirrored)' % (
            C.props.get('BOARD_NAME', C.pname), C.revision)})
        with open(C.put(out), 'wb') as f:
            w.write(f)
        n = page_count(out)
        C.check('assembly PDF: 2 pages (top, bottom mirrored)', n == 2, plural(n, 'page'))
        sheets = [(out, 0, 1), (out, 1, 2)]
        summary = plural(n, 'page')
    found = ''
    if hasattr(C, 'xyrs_rows'):
        fitz = import_pymupdf()
        if fitz is None:
            C.check('assembly PDF: designators not checked (no PyMuPDF)', False, level='warn')
        else:
            miss = []
            for path, page, side in sheets:
                doc = fitz.open(path)
                try:
                    words = {w[4] for w in doc[page].get_text('words')} if page < doc.page_count else set()
                finally:
                    doc.close()
                miss += [r['ref'] for r in C.xyrs_rows if r['side'] == side and r['ref'] not in words]
            C.check('assembly PDF: every XYRS designator is printed on its side\'s page (%d)' % len(C.xyrs_rows),
                    not miss, 'missing ' + ' '.join(miss[:20]) if miss else '')
            found = ', all %d designators found' % len(C.xyrs_rows) if not miss else ', %d missing' % len(miss)
    return summary + found


def import_pymupdf():
    """The PyMuPDF module (real word boxes; pypdf runs the Fab texts together), or None when it is not installed."""
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # PyMuPDF before 1.24.3 has only the old module name
        except ImportError:
            return None
    return fitz


def resolve_model(fn, proj, env):
    def sub(m):
        return proj if m.group(1) == 'KIPRJMOD' else env.get(m.group(1), m.group(0))
    p = re.sub(r'\$\{([^}]+)\}', sub, fn)
    if '${' in p:
        return None
    if not os.path.isabs(p):
        p = os.path.join(proj, p)
    cands = [p]
    if p.lower().endswith('.wrl'):
        cands += [p[:-4] + e for e in ('.step', '.stp', '.STEP', '.STP')]
    return next((c for c in cands if os.path.isfile(c)), None)


def step_step(C):
    a = C.a
    out = C.put(os.path.join(C.out, 'docs', '%s.step' % C.prefix))
    x0, y1 = C.origin
    origin = '%sx%smm' % (('%.6f' % x0).rstrip('0').rstrip('.'), ('%.6f' % y1).rstrip('0').rstrip('.'))
    args = ['pcb', 'export', 'step', '--force', '--subst-models', '--min-distance', '0.01mm', '--user-origin', origin]
    if not a.step_with_dnp:
        args.append('--no-dnp')
    flat = []   # bare file names, copied into the project folder only where the part has no other model
    for fp in C.pcb['footprints']:
        shown = [m for m in fp['models'] if m['show']]
        if not shown or not getattr(C, 'models_ok', False) or any(resolve_model(m['file'], C.proj, C.env) for m in shown):
            continue
        for m in shown:
            src = os.path.join(C.models_staging, m['file'])
            if not re.search(r'[\\/]|\$\{', m['file']) and os.path.isfile(src):
                shutil.copyfile(src, os.path.join(C.proj, m['file']))
                flat.append('%s: %s' % (fp['ref'], m['file']))
    log = C.kcli(*args, '-o', out, C.board)
    if not os.path.exists(out):
        raise StepError('no STEP written')
    cli_missing = re.findall(r'Could not add 3D model for ([^\s.]+)\.\s*\n?(?:File not found: ([^\n]+))?', log)
    # resolve every model entry the STEP would use
    entries = missing = 0
    missing_files, no_model, all_missing, dup = [], [], [], []
    resolved_refs = set()
    for fp in C.pcb['footprints']:
        if fp['n_pads'] == 0 or (fp['dnp'] and not a.step_with_dnp):
            continue
        shown = [m for m in fp['models'] if m['show']]
        if not shown:
            if not (C.non_part_refs and C.non_part_refs.match(fp['ref'])) and \
                    not C.comps.get(fp['ref'], {}).get('exclude_bom'):
                no_model.append(fp['ref'])
            continue
        res = []
        for m in shown:
            entries += 1
            r = resolve_model(m['file'], C.proj, C.env)
            if r is None:
                missing += 1
                missing_files.append('%s: %s' % (fp['ref'], m['file']))
            res.append(r)
        got = [os.path.basename(r).lower() for r in res if r]
        if got:
            resolved_refs.add(fp['ref'])
        if len(got) != len(set(got)):
            dup.append(fp['ref'])
        if not got:
            all_missing.append(fp['ref'])
    with open(out, encoding='latin-1') as f:
        nauo = set(re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('[^']*','([^']*)'", f.read()))
    in_step = {r for r in nauo if r in C.fp}
    C.models = {'entries': entries, 'missing_entries': missing, 'missing_files': missing_files,
                'fitted_parts_without_model': no_model, 'parts_with_every_model_missing': all_missing,
                'parts_with_the_same_model_twice': sorted(dup, key=natural_key), 'flat_copies_added': flat,
                'kicad_cli_could_not_add': ['%s %s' % (r, f.strip()) for r, f in cli_missing],
                'parts_in_step': len(in_step), 'library': C.models_status}
    C.check('STEP: components in the file = parts with a resolved model (%d)' % len(resolved_refs),
            in_step == resolved_refs, 'only STEP %s; missing %s' % (sorted(in_step - resolved_refs)[:8],
                                                                     sorted(resolved_refs - in_step)[:8]), level='warn')
    if dup:
        C.check('STEP: parts whose footprint lists the same model file twice (two coincident bodies)', False,
                ' '.join(sorted(dup, key=natural_key)), level='warn')
    if C.s.library_dir:
        C.check('STEP: %s 3-D models added to the project copy' % C.s.library_dir, C.models_ok, C.models_status)
    C.check('STEP: every placed part with a model entry gets a model', not all_missing, ' '.join(all_missing))
    partial = [m for m in missing_files if m.split(':', 1)[0] not in all_missing]   # all_missing: the check above
    if partial:
        C.check('STEP: %d model entries do not resolve (each of these parts has another entry that does)'
                % len(partial), False, '; '.join(partial), level='warn')
    if no_model:
        C.check('STEP: fitted parts with no 3-D model in their footprint', False, ' '.join(no_model), level='warn')
    # origin check on a board-only export
    bo = os.path.join(C.work, 'board_only.step')
    C.kcli('pcb', 'export', 'step', '--force', '--board-only', '--user-origin', origin, '-o', bo, C.board)
    pts = [tuple(float(v) for v in m.group(1).split(','))
           for m in re.finditer(r"CARTESIAN_POINT\('[^']*',\(([^)]*)\)\)", read_text(bo))]
    bx0, bx1 = min(p[0] for p in pts), max(p[0] for p in pts)
    by0, by1 = min(p[1] for p in pts), max(p[1] for p in pts)
    w_mm, h_mm = C.size_mil[0] * MIL, C.size_mil[1] * MIL
    ok = max(abs(bx0), abs(by0), abs(bx1 - w_mm), abs(by1 - h_mm)) < 0.01
    C.check('STEP: origin = XYRS corner (board spans 0..%.3f x 0..%.3f mm)' % (w_mm, h_mm), ok,
            'board-only STEP x %.3f..%.3f y %.3f..%.3f' % (bx0, bx1, by0, by1))
    C.counts['step_mb'] = round(os.path.getsize(out) / 1e6, 1)
    return '%.1f MB; %d model entries, %d unresolved (%s); fitted parts without a model: %s; origin %s' % (
        C.counts['step_mb'], entries, missing, '; '.join(missing_files) or '-', ' '.join(no_model) or 'none', origin)


def step_odb(C):
    out = C.put(os.path.join(C.out, 'fab', '%s_odb.zip' % C.prefix))
    C.kcli('pcb', 'export', 'odb', '--compression', 'zip', '--units', 'mm', '--precision', '2', '-o', out, C.board)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        comp = sum(z.read(n).decode('utf-8', 'replace').count('\nCMP ') for n in names if n.endswith('/components'))
        fill = [n for n in names if '/layers/filling' in n and n.endswith('/features')]
        fill_pads = sum(len(re.findall(r'^P ', z.read(n).decode('utf-8', 'replace'), re.M)) for n in fill)
    n_fp = sum(1 for fp in C.pcb['footprints'] if not fp['exclude_pos'] and fp['n_pads'])
    C.check('ODB++: components = placed footprints (%d)' % n_fp, comp == n_fp, '%d CMP records' % comp, level='warn')
    C.check('ODB++: filling layer carries the filled vias', fill_pads == len(C.filled_vias) if hasattr(C, 'filled_vias')
            else bool(fill), '%d pads in %s' % (fill_pads, fill), level='warn')
    return '%d members, %d components, filling layer %d pads' % (len(names), comp, fill_pads)


IBOM_RUNNER = r'''
import os, sys
pkg = sys.argv[1]
sys.path.insert(0, pkg)
os.environ['INTERACTIVE_HTML_BOM_CLI_MODE'] = '1'
os.environ['INTERACTIVE_HTML_BOM_NO_DISPLAY'] = '1'
sys.argv = ['generate_interactive_bom'] + sys.argv[2:]   # set before the import: the package registers a GUI plugin otherwise
from InteractiveHtmlBom import generate_interactive_bom
sys.exit(generate_interactive_bom.main())
'''


def step_ibom(C):
    a = C.a
    if not a.ibom_pkg:
        C.check('iBOM: skipped (no --ibom-pkg)', False, level='warn')
        return 'skipped'
    pkg = os.path.abspath(a.ibom_pkg)
    if not os.path.isfile(os.path.join(pkg, 'InteractiveHtmlBom', 'generate_interactive_bom.py')):
        raise StepError('--ibom-pkg %s has no InteractiveHtmlBom/generate_interactive_bom.py' % pkg)
    runner = os.path.join(C.work, 'ibom_runner.py')
    with open(runner, 'w', encoding='utf-8') as f:
        f.write(IBOM_RUNNER)
    dest = os.path.join(C.out, 'assembly')
    name = '%s_ibom' % C.prefix
    C.run([C.kpy, '-I', runner, pkg, '--no-browser', '--dest-dir', dest, '--name-format', name, '--include-tracks',
           '--include-nets', '--extra-fields', 'MPN', '--show-fields', 'Value,Footprint,MPN', '--group-fields',
           'Value,Footprint,MPN', '--checkboxes', 'Placed', '--layer-view', 'FB', '--dnp-field', 'kicad_dnp',
           '--highlight-pin1', 'all', C.board])
    out = os.path.join(dest, name + '.html')
    if not os.path.exists(out):
        raise StepError('iBOM wrote no ' + out)
    C.put(out)
    html = read_text(out)
    m = re.search(r'LZString\.decompressFromBase64\(("(?:[^"\\]|\\.)*")\)', html)
    if m:
        data = json.loads(lz_decompress_b64(json.loads(m.group(1))))
    else:
        m = re.search(r'var pcbdata = (\{.*?\});?\n', html, re.S)
        data = json.loads(m.group(1))
    bom = data['bom']
    refs = {r[0] for g in bom['both'] for r in g}
    nf, nb = sum(len(g) for g in bom['F']), sum(len(g) for g in bom['B'])
    pop1 = {r['ref'] for r in C.xyrs_rows if r['pop']} if hasattr(C, 'xyrs_rows') else set()
    C.check('iBOM: BOM parts = XYRS Populate 1 (%d; %d top / %d bottom)' % (len(pop1), C.counts.get('fitted_top', -1),
                                                                         C.counts.get('fitted_bottom', -1)),
            refs == pop1 and nf == C.counts.get('fitted_top') and nb == C.counts.get('fitted_bottom'),
            'iBOM %d refs (%d F / %d B), %d lines; only iBOM %s; only XYRS %s' % (
                len(refs), nf, nb, len(bom['both']), sorted(refs - pop1)[:8], sorted(pop1 - refs)[:8]))
    C.check('iBOM: title block revision = %s' % C.revision, data['metadata'].get('revision') == C.revision,
            str(data['metadata']))
    m = re.search(r'var config = (\{.*?\})\s*\n', html)
    cfg = json.loads(m.group(1)) if m else {}
    C.check('iBOM: pin 1 highlighted on every part (highlight_pin1 = all)', cfg.get('highlight_pin1') == 'all',
            'config highlight_pin1 = %r' % cfg.get('highlight_pin1'), level='warn')
    C.counts['ibom_lines'] = len(bom['both'])
    dist = [d for d in os.listdir(pkg) if d.lower().startswith('interactivehtmlbom') and d.endswith('.dist-info')]
    C.ibom_version = dist[0][:-len('.dist-info')] if dist else 'InteractiveHtmlBom (version unknown)'
    return '%s: %d lines, %d parts (%d F / %d B), %d skipped footprints, %.1f MB' % (
        C.ibom_version, len(bom['both']), len(refs), nf, nb, len(bom['skipped']), os.path.getsize(out) / 1e6)


def write_layer_map(C):
    path = C.put(os.path.join(C.out, 'fab', '%s_layer_map.csv' % C.prefix))
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['order', 'kicad_layer', 'board_layer_name', 'function', 'polarity', 'fab_file', 'kicad_file',
                    'upload_file'])
        for i, s in enumerate(C.gerbers, 1):
            w.writerow([i, s['layer'], s['board_name'], s['function'], s['polarity'], s['fab_file'], s['kicad_file'],
                        s['upload_file']])
        for kind, label in (('PTH', 'Plated holes, not filled'), ('PTH_FILLED', 'Plated + Filled/Plugged, Non-Conductive (IPC-4761 VII)'),
                            ('NPTH', 'Non-plated holes')):
            w.writerow(['', 'drill', '', label, '', '%s_%s.drl' % (C.prefix, kind), '', '%s_%s.XLN' % (C.upload_base, kind)])
    return path


def build_zip(C, manifest):
    """The upload zip from the files already in DIR (manifest['layer_map'])."""
    prefix = manifest['name']
    base = manifest.get('upload_base') or upload_base(prefix)
    out = os.path.join(C.out, '%s_macrofab_upload.zip' % prefix)
    members = upload_members(C.out, prefix, manifest['layer_map'], base)
    xyrs = os.path.join(C.out, 'assembly', '%s.XYRS' % prefix)
    xlsx = os.path.join(C.out, 'bom', '%s_macrofab.xlsx' % prefix)
    arcs = [arc for _, arc in members]
    bad_names = [a for a in arcs if a.count('.') != 1 or not a.startswith(base) or '/' in a or ' ' in a]
    C.check('upload zip: member names are flat, start with %s and have exactly one dot (before the extension)' % base,
            not bad_names and len(set(a.lower() for a in arcs)) == len(arcs), ' '.join(bad_names))
    if os.path.exists(xlsx):
        if check_xlsx(C, xlsx, xyrs) is False:
            raise StepError('the xlsx and the XYRS disagree: upload zip NOT written%s' % (
                ' (the existing %s is now out of date)' % os.path.basename(out) if os.path.exists(out) else ''))
    else:
        C.check('upload zip: no %s yet (run kicad-macrofab-bom, then kicad-fab-export --zip-only)'
                % os.path.relpath(xlsx, C.out).replace(os.sep, '/'), False, level='warn')
    missing = [src for src, _ in members if not os.path.exists(src)]
    if missing:
        raise StepError('zip members missing: %s' % missing)
    stamp = kproject.iso_datetime(manifest['commit_date']).timetuple()[:6]
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, arc in members:
            zi = zipfile.ZipInfo(arc, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(src, 'rb') as f:
                z.writestr(zi, f.read())
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        bad = z.testzip()
        differ = [arc for src, arc in members if hashlib.sha256(z.read(arc)).hexdigest() != sha256(src)]
    C.check('upload zip: %d members, CRC ok, byte-identical to the package files, no PDF / ODB++ / gbrjob' % len(names),
            bad is None and not differ and not [n for n in names if re.search(r'\.(pdf|zip|gbrjob|tgz)$', n, re.I)],
            ', '.join(names) + ('; differ: %s' % differ if differ else ''))
    C.outputs.append(out)
    return out, names


def check_xlsx(C, xlsx, xyrs):
    try:
        import openpyxl
    except ImportError:
        C.check('xlsx vs XYRS: openpyxl missing, not checked', False, level='warn')
        return
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    try:
        rows = list(wb.worksheets[0].iter_rows(values_only=True))
    finally:
        wb.close()   # a read-only workbook keeps the file open until closed

    hdr = [str(h or '').strip() for h in rows[0]]
    if 'Designator' not in hdr:
        return C.check('xlsx vs XYRS: xlsx has a Designator column', False, str(hdr))
    di, pi = hdr.index('Designator'), (hdr.index('Populate') if 'Populate' in hdr else None)
    x = {str(r[di]).strip(): (None if pi is None else str(r[pi]).strip()) for r in rows[1:] if r[di]}
    y = {}
    with open(xyrs, encoding='ascii') as f:
        for l in f:
            if not l.startswith('#'):
                p = l.rstrip('\n').split('\t')
                y[p[0]] = p[10]
    dup = len([r for r in rows[1:] if r[di]]) - len(x)
    pop_diff = [k for k in x if k in y and x[k] is not None and x[k] not in (y[k], y[k] + '.0')]
    return C.check('xlsx vs XYRS: same designators (%d), unique, same Populate' % len(y),
            set(x) == set(y) and not dup and not pop_diff,
            'only xlsx %s; only XYRS %s; duplicates %d; Populate differs %s' % (
                sorted(set(x) - set(y), key=natural_key)[:10], sorted(set(y) - set(x), key=natural_key)[:10], dup,
                pop_diff[:10]))


def check_line(c):
    """One check as --zip-only prints it: status, name and, for a failed check, its detail."""
    tag = 'ok' if c['ok'] else ('FAIL' if c['level'] == 'error' else 'WARN')
    return '%-5s %s%s' % (tag, c['name'], (' - ' + str(c['detail'])) if c['detail'] and not c['ok'] else '')


def file_table(C, paths):
    rows = []
    for p in sorted(set(paths)):
        if os.path.exists(p):
            rows.append({'path': os.path.relpath(p, C.out).replace('\\', '/'), 'bytes': os.path.getsize(p),
                         'sha256': sha256(p)})
    return rows


def package_tables(C, mpath, written):
    """(outputs, other_files): sha256 tables of the files this tool wrote (written: absolute paths or paths relative
    to DIR) and of every other file in DIR (bom/, README.md, stray files), the manifest itself left out."""
    allf = [os.path.join(r, f) for r, _, fs in os.walk(C.out) for f in fs]
    mine = {os.path.normcase(os.path.join(C.out, p)) for p in written}
    skip = os.path.normcase(os.path.abspath(mpath))
    outs = [p for p in allf if os.path.normcase(p) in mine and os.path.normcase(p) != skip]
    other = [p for p in allf if os.path.normcase(p) not in mine and os.path.normcase(p) != skip]
    return file_table(C, outs), file_table(C, other)


def refs_containing(repo, sha):
    """Branches, remote branches and tags that contain sha (empty: a scratch commit on no ref)."""
    out = kproject.git(repo, 'for-each-ref', '--contains', sha, '--format=%(refname)', check=False)
    return [l for l in out.splitlines() if l.strip()]


CONFIG_KEYS = ('project_dir', 'name_template', 'library_dir', 'library_paths', 'library_model_paths',
               'generator_prefix', 'require_dru', 'kicad_cli', 'kicad_python', 'kicad_3dmodel_dir', 'ibom_pkg',
               'non_part_refs', 'non_part_libs', 'xyrs_non_part_refs', 'xyrs_non_part_libs', 'require_filled_vias')


def build_parser():
    ap = argparse.ArgumentParser(prog='kicad-fab-export', description=config.cli_description(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rev', nargs='?', metavar='REV', help='the commit to export: any commit-ish (HEAD, a branch, a '
                                                          'tag, a hash); required except with --zip-only')
    ap.add_argument('--out', required=True, metavar='DIR', help='the package folder (created if needed); fab/, '
                                                                'assembly/ and docs/ must be empty unless --force')
    ap.add_argument('--repo', default='.', metavar='DIR', help='the git repository (default: the current folder)')
    ap.add_argument('--no-zip', action='store_true', help='do not write the upload zip')
    ap.add_argument('--zip-only', action='store_true', help='only re-pack the upload zip from the files already in '
                                                            '--out and refresh the manifest (no REV, no KiCad)')
    ap.add_argument('--name', help='output name prefix (default: the name template)')
    ap.add_argument('--work', metavar='DIR', help='work folder, kept (an empty or new folder); default: a temp '
                                                  'folder removed on success')
    ap.add_argument('--keep-work', action='store_true', help='keep the temp work folder on success too')
    ap.add_argument('--expect', default='', metavar='KEY=N,...',
                    help='fail unless these counts hold; KEY in ' + ', '.join(EXPECT_KEYS))
    ap.add_argument('--step-with-dnp', action='store_true', help='keep DNP parts in the STEP')
    ap.add_argument('--force', action='store_true', help='write into non-empty fab/ assembly/ docs/ (same names '
                                                         'are overwritten, other files are left and listed)')
    ap.add_argument('--accept-dnp-paste', default='', metavar='REFS',
                    help='comma list of Populate 0 parts whose paste is accepted (a warning and a note instead of an '
                         'error); only when the board cannot change and MacroFab is told "no paste at REFS"')
    config.add_args(ap, CONFIG_KEYS)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    ap = build_parser()
    a = ap.parse_args(argv)
    C = Ctx(a)
    C.out = os.path.abspath(a.out)
    os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    sys.dont_write_bytecode = True

    if a.zip_only:
        docs = os.path.join(C.out, 'docs')
        mans = [f for f in os.listdir(docs) if f.endswith('_export_manifest.json')] if os.path.isdir(docs) else []
        if len(mans) != 1:
            print('ERROR: --zip-only needs exactly one docs/*_export_manifest.json in', config.show_path(C.out))
            return 2
        mpath = os.path.join(docs, mans[0])
        try:
            with open(mpath, encoding='utf-8') as f:
                manifest = json.load(f)
            for key in ('name', 'layer_map', 'commit_date', 'checks'):
                if key not in manifest:
                    raise ValueError('no %r key' % key)
        except (OSError, ValueError) as e:
            print('ERROR: %s is not a kicad-fab-export manifest: %s' % (config.show_path(mpath), e))
            return 2
        try:
            out, names = build_zip(C, manifest)
        except StepError as e:
            for c in C.checks:
                print(check_line(c))
            print('ERROR:', e)
            return 1
        manifest['upload_zip'] = {'path': os.path.basename(out), 'members': names, 'bytes': os.path.getsize(out),
                                  'sha256': sha256(out)}
        manifest['checks'] = [c for c in manifest['checks'] if not c['name'].startswith(('upload zip', 'xlsx vs'))] + C.checks
        manifest['outputs'], manifest['other_files'] = package_tables(
            C, mpath, [o['path'] for o in manifest.get('outputs', [])] + [out])
        manifest = C.portable(manifest)
        with open(mpath, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(manifest, f, indent=1)
            f.write('\n')
        for c in C.checks:
            print(check_line(c))
        print('wrote %s (%d members, %d bytes)' % (config.show_path(out), len(names), os.path.getsize(out)))
        return 1 if any(not c['ok'] and c['level'] == 'error' for c in C.checks) else 0

    if not a.rev:
        ap.error('REV is required (except with --zip-only)')
    expect = {}
    for kv in filter(None, a.expect.split(',')):
        k, _, v = kv.partition('=')
        if k not in EXPECT_KEYS or not v.isdigit():
            ap.error('bad --expect item %r' % kv)
        expect[k] = int(v)
    try:
        C.s = cfg = config.resolve(a, a.repo)
        a.ibom_pkg = cfg.ibom_pkg
        C.generator = cfg.generator_prefix + TOOL
        C.non_part_refs = config.compile_refs(cfg.xyrs_non_part_refs)
        C.non_part_libs = tuple(cfg.xyrs_non_part_libs)
        C.cli = kproject.kicad_cli(cfg.kicad_cli)
        C.kpy = config.find_kicad_python(cfg.kicad_python, C.cli)
        if not C.kpy or not os.path.exists(C.kpy):
            raise SetupError("KiCad python not found: %s (--kicad-python, KICAD_PYTHON or KICAD10_PYTHON)" % (
                C.kpy or 'none next to kicad-cli or in the standard install folders'))
        C.repo = os.path.abspath(a.repo)
        C.top = kproject.git(C.repo, 'rev-parse', '--show-toplevel')
        C.sha = kproject.rev_sha(C.repo, a.rev)
        C.subject, C.commit_date = kproject.git(C.repo, 'log', '-1', '--format=%s%n%cI', C.sha).split('\n')[:2]
        common = kproject.git(C.repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')
        C.main_checkout = os.path.dirname(os.path.abspath(common))
        C.refs = refs_containing(C.repo, C.sha)
        for sub in ('fab', 'assembly', 'docs'):
            d = os.path.join(C.out, sub)
            if os.path.isdir(d) and os.listdir(d) and not a.force:
                raise SetupError('%s is not empty (use --force to overwrite same-named files)'
                                 % config.show_path(d))
            os.makedirs(d, exist_ok=True)
        before = {os.path.join(C.out, s, f) for s in ('fab', 'assembly', 'docs') for f in os.listdir(os.path.join(C.out, s))}
    except (kproject.ProjectError, config.ConfigError, SetupError) as e:
        print('ERROR:', e)
        return 2
    own_work = not a.work
    C.work = os.path.abspath(a.work) if a.work else tempfile.mkdtemp(prefix='export_fab_')
    if a.work:
        if os.path.exists(C.work) and os.listdir(C.work):
            print('ERROR: --work %s is not empty' % config.show_path(C.work))
            return 2
        os.makedirs(C.work, exist_ok=True)
    tmp = os.path.join(C.work, 'tmp')
    os.makedirs(tmp, exist_ok=True)
    C.env = dict(os.environ, TEMP=tmp, TMP=tmp, PYTHONDONTWRITEBYTECODE='1')
    models_dir = config.find_kicad_3dmodel_dir(cfg.kicad_3dmodel_dir, C.cli)
    if models_dir and a.kicad_3dmodel_dir:      # the flag wins over the environment
        C.env['KICAD9_3DMODEL_DIR'] = C.env['KICAD10_3DMODEL_DIR'] = models_dir
    elif models_dir:
        C.env.setdefault('KICAD9_3DMODEL_DIR', models_dir)
        C.env.setdefault('KICAD10_3DMODEL_DIR', models_dir)
    C.kicad_version = 'KiCad ' + subprocess.run([C.cli, 'version'], capture_output=True, text=True).stdout.strip()

    plan = [('project copy', step_project, []), ('board facts', step_board_facts, ['project copy']),
            ('pcbnew facts', step_pcbnew, ['project copy']), ('schematic facts', step_schematic, ['project copy']),
            ('gerbers', step_gerbers, ['board facts', 'pcbnew facts']),
            ('drill', step_drill, ['gerbers']),
            ('placement (XYRS, pos)', step_placement, ['board facts', 'pcbnew facts', 'schematic facts']),
            ('paste on unplaced parts', step_paste, ['gerbers', 'placement (XYRS, pos)']),
            ('schematic PDF', step_sch_pdf, ['board facts']),
            ('assembly PDF', step_assembly_pdf, ['board facts']),
            ('STEP', step_step, ['board facts', 'pcbnew facts', 'schematic facts']),
            ('ODB++', step_odb, ['board facts', 'pcbnew facts']),
            ('iBOM', step_ibom, ['board facts', 'placement (XYRS, pos)'])]
    status = {}
    for name, fn, deps in plan:
        bad = [d for d in deps if status.get(d) != 'ok']
        if bad:
            status[name] = 'skip'
            C.steps.append((name, 'SKIP', 'needs ' + ', '.join(bad)))
            continue
        print('--', name, flush=True)
        try:
            detail = fn(C)
            status[name] = 'ok'
            C.steps.append((name, 'ok', detail))
        except (StepError, Exception) as e:  # noqa: BLE001
            status[name] = 'fail'
            msg = str(e) if isinstance(e, StepError) else traceback.format_exc(limit=4)
            C.steps.append((name, 'FAIL', C.short(msg)))

    for k, v in expect.items():
        got = {'fitted': C.counts.get('fitted'), 'rows': C.counts.get('xyrs_rows'), 'pop0': C.counts.get('pop0'),
               'fitted_top': C.counts.get('fitted_top'), 'fitted_bottom': C.counts.get('fitted_bottom'),
               'pth': C.counts.get('drill_pth'), 'filled': C.counts.get('drill_filled'),
               'npth': C.counts.get('drill_npth'), 'pages': C.counts.get('schematic_pages')}[k]
        C.check('expect %s = %d' % (k, v), got == v, 'got %s' % got)
    C.check('source commit is on a branch or tag (its hash and subject go into the XYRS header, the manifest and the '
            'zip dates)', bool(C.refs),
            ', '.join(C.refs[:6]) if C.refs else 'commit %s is on NO branch or tag: a scratch commit. Do not commit '
            'these outputs; re-run on the final commit' % C.sha[:9], level='warn')

    manifest = None
    if status.get('gerbers') == 'ok':
        try:
            write_layer_map(C)
            manifest = collections.OrderedDict([
                ('name', C.prefix), ('board', C.props.get('BOARD_NAME')), ('revision', C.revision),
                ('release_date', C.props.get('RELEASE_DATE')), ('commit', C.sha), ('subject', C.subject),
                ('commit_date', C.commit_date), ('refs_containing_commit', C.refs[:20]),
                ('kicad', C.kicad_version), ('generator', C.generator),
                ('upload_base', C.upload_base),
                ('ibom', getattr(C, 'ibom_version', None)), ('library', getattr(C, 'library_status', None)),
                ('xyrs_origin_kicad_mm', list(C.origin)), ('board_size_mil', [round(v, 2) for v in C.size_mil]),
                ('board_size_mm', [round(v * MIL, 4) for v in C.size_mil]),
                ('aux_origin_mm_not_used', C.pcb['aux_origin_mm']), ('plot_params', C.plot_params),
                ('forced_x1', C.forced_x1),
                ('layer_map', [{k: s[k] for k in ('layer', 'board_name', 'function', 'polarity', 'kicad_file',
                                                  'fab_file', 'upload_file')} for s in C.gerbers]),
                ('filled_vias', getattr(C, 'filled_vias', None)), ('fiducials', getattr(C, 'fiducials', None)),
                ('xyrs_omitted', getattr(C, 'omitted', None)), ('board_only_logos', getattr(C, 'logos', None)),
                ('paste', getattr(C, 'paste', None)), ('xyrs_body_offsets', getattr(C, 'body_offsets', None)),
                ('xyrs_pad1', getattr(C, 'pin1', None)), ('models', getattr(C, 'models', None)),
                ('counts', C.counts), ('notes', C.notes), ('steps', [list(s) for s in C.steps]),
                ('commands', C.commands)])
        except Exception:  # noqa: BLE001
            C.steps.append(('manifest', 'FAIL', traceback.format_exc(limit=3)))
    if manifest is not None and not a.no_zip:
        needed = ('gerbers', 'drill', 'placement (XYRS, pos)')
        if all(status.get(n) == 'ok' for n in needed):
            try:
                out, names = build_zip(C, manifest)
                manifest['upload_zip'] = {'path': os.path.basename(out), 'members': names,
                                          'bytes': os.path.getsize(out), 'sha256': sha256(out)}
                C.steps.append(('upload zip', 'ok', '%d members' % len(names)))
            except (StepError, Exception) as e:  # noqa: BLE001
                C.steps.append(('upload zip', 'FAIL', str(e)))
        else:
            C.steps.append(('upload zip', 'SKIP', 'needs ' + ', '.join(needed)))
    if manifest is not None:
        mpath = C.put(os.path.join(C.out, 'docs', '%s_export_manifest.json' % C.prefix))
        manifest['checks'] = C.checks
        manifest['outputs'], manifest['other_files'] = package_tables(C, mpath, [p for p in C.outputs if p != mpath])
        manifest = C.portable(manifest)
        with open(mpath, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(manifest, f, indent=1)
            f.write('\n')

    # summary
    print('\n== %s from %s (%s) -> %s' % (getattr(C, 'prefix', '?'), C.sha[:9], C.subject[:70],
                                          config.show_path(C.out)))
    print('\nsteps:')
    for name, st, detail in C.steps:
        print(('  %-4s %-22s %s' % (st, name, detail)).rstrip())
    print('\nfiles:')
    for r in file_table(C, C.outputs):
        print('  %10d  %s' % (r['bytes'], r['path']))
    stray = sorted(p for p in before if p not in set(C.outputs) and os.path.exists(p))
    if stray:
        print('\nfiles in DIR not written by this run (left as they were):')
        for p in stray:
            print('  ', config.show_path(os.path.relpath(p, C.out)))
    print('\ncounts:')
    for k, v in C.counts.items():
        print('  %-16s %s' % (k, v))
    print('\nchecks:')
    for c in C.checks:
        tag = 'ok' if c['ok'] else ('FAIL' if c['level'] == 'error' else 'WARN')
        d = str(c['detail'])
        print('  %-4s %s%s' % (tag, c['name'], ('  -- ' + (d if len(d) < 400 else d[:400] + ' ...')) if d else ''))
    for n in C.notes:
        print('NOTE:', n)
    failed = [s for s in C.steps if s[1] == 'FAIL'] + [c for c in C.checks if not c['ok'] and c['level'] == 'error']
    if failed:
        print('\nRESULT: FAILED (%d failed steps/checks); work folder kept: %s'
              % (len(failed), config.show_path(C.work)))
        return 1
    if own_work and not a.keep_work:
        shutil.rmtree(C.work, ignore_errors=True)
    else:
        print('work folder:', config.show_path(C.work))
    print('\nRESULT: ok (%d warnings)' % sum(1 for c in C.checks if not c['ok']))
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--pcbnew-dump':
        pcbnew_dump(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if config is None:
        sys.exit('run this as `kicad-fab-export` or `python -m kicad_fab_package.export_fab`')
    sys.exit(main())
