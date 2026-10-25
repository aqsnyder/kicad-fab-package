import argparse
import collections
import io
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest import mock

from kicad_fab_package import export_fab as ef

from ._util import rmtree

GERBER = '''G04 #@! TF.GenerationSoftware,KiCad,Pcbnew,10.0.7*
G04 Created by KiCad (PCBNEW 10.0.7) date 2026-01-01 00:00:00*
%FSLAX46Y46*%
G04 Gerber Fmt 4.6, Leading zero omitted, Abs format (unit mm)*
%MOMM*%
%LPD*%
G01*
G04 APERTURE LIST*
%ADD10C,0.100000*%
%ADD11R,1.000000X2.000000*%
G04 APERTURE END LIST*
D10*
X1000000Y-2000000D02*
X3000000Y-2000000D01*
D11*
X5000000Y-5000000D03*
G36*
X0Y0D02*
X1000000Y0D01*
X1000000Y1000000D01*
X0Y0D01*
G37*
%LPC*%
X6000000Y-6000000D03*
M02*
'''

EXCELLON = '''M48
; DRILL file {KiCad 10.0.7} date 2026-01-01T00:00:00
; FORMAT={-:-/ absolute / metric / decimal}
; #@! TF.FileFunction,Plated,1,4,PTH
FMAT,2
METRIC
; #@! TA.AperFunction,Plated,PTH,ViaDrill
T1C0.300
; #@! TA.AperFunction,Plated,PTH,ComponentDrill
T2C1.000
%
G90
G05
T1
X10.0Y-5.0
X12.0Y-5.0
T2
X20.0Y-8.0
M30
'''

BOARD_VIAS = '''(kicad_pcb
\t(version 20250000)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t\t(capping yes)
\t)
\t(via
\t\t(at 10 5)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "B.Cu")
\t\t(filling yes)
\t\t(net "GND")
\t\t(uuid "v1")
\t)
\t(via blind
\t\t(at 12 5)
\t\t(size 0.6)
\t\t(drill 0.3)
\t\t(layers "F.Cu" "In1.Cu")
\t\t(capping no)
\t\t(net "GND")
\t\t(uuid "v2")
\t)
)
'''


def write(path, text, newline='\n'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline=newline) as f:
        f.write(text)
    return path


class TmpDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kfp_test_')

    def tearDown(self):
        rmtree(self.tmp)


class XyrsRulesTest(unittest.TestCase):
    def test_rotation_top_is_kicad_orientation(self):
        for ori, want in ((0, 0), (90, 90), (180, 180), (270, 270), (-90, 270), (450, 90)):
            self.assertEqual(ef.xyrs_rotation(ori, 1)[1], want, ori)

    def test_rotation_bottom_adds_180(self):
        for ori, want in ((0, 180), (90, 270), (180, 0), (270, 90), (-90, 90)):
            self.assertEqual(ef.xyrs_rotation(ori, 2)[1], want, ori)

    def test_rotation_rounding(self):
        raw, rot = ef.xyrs_rotation(89.996, 1)
        self.assertAlmostEqual(raw, 89.996)
        self.assertEqual(rot, 90)
        self.assertEqual(ef.xyrs_rotation(359.7, 1)[1], 0)   # rounds to 360 -> 0

    def test_point_origin_bottom_left_y_up(self):
        origin = (100.0, 50.0)        # (left, bottom) in KiCad mm, Y down
        self.assertEqual(ef.xyrs_point(100.0, 50.0, origin), (0.0, 0.0))
        x, y = ef.xyrs_point(100.0 + 25.4, 50.0 - 25.4, origin)   # 1 inch right, 1 inch up
        self.assertAlmostEqual(x, 1000.0)
        self.assertAlmostEqual(y, 1000.0)

    def test_non_part_and_dnp_words(self):
        self.assertTrue(ef.NON_PART_RE.match('FID1'))
        self.assertTrue(ef.NON_PART_RE.match('H12'))
        self.assertFalse(ef.NON_PART_RE.match('HS1'))
        self.assertTrue(ef.DNP_WORD_RE.search('ABC1001dnpR'))
        self.assertFalse(ef.DNP_WORD_RE.search('DN1'))

    def test_non_part_rule_is_configurable(self):
        import re
        self.assertTrue(ef.is_non_part('FID1', 'Custom:Fid'))
        self.assertTrue(ef.is_non_part('P1', 'Fiducial:Fiducial_1mm'))
        # designator only (no library match), library only (no designator match), neither
        self.assertFalse(ef.is_non_part('P1', 'Fiducial:Fiducial_1mm', ef.NON_PART_RE, ()))
        self.assertFalse(ef.is_non_part('FID1', 'Custom:Fid', None, ef.NON_PART_LIBS))
        self.assertTrue(ef.is_non_part('MH2', 'Mech:Hole', re.compile(r'MH\d+$'), ()))
        self.assertFalse(ef.is_non_part('FID1', 'Fiducial:F', None, ()))

    def test_fiducials_line_by_designator_or_kicad_library(self):
        self.assertTrue(ef.is_fiducial('FID3', 'Custom:Mark'))
        self.assertTrue(ef.is_fiducial('FD1', 'Fiducial:Fiducial_1mm_Mask2mm'))
        self.assertFalse(ef.is_fiducial('H1', 'MountingHole:MountingHole_3.2mm_M3'))
        self.assertFalse(ef.is_fiducial('FD1', 'Custom:Fiducial_1mm'))       # library name, not footprint name


class FilledViaChecksTest(unittest.TestCase):
    def test_board_without_filled_vias(self):
        groups = {('none', 'none'): {(1.0, 2.0)}}
        self.assertTrue(ef.filled_vias_seen(set(), groups))
        self.assertTrue(ef.filled_vias_found([], []))
        self.assertFalse(ef.filled_vias_seen(set(), groups, required=True))
        self.assertFalse(ef.filled_vias_seen(set(), {}, required=True))
        self.assertFalse(ef.filled_vias_found([], [], required=True))

    def test_board_with_filled_vias(self):
        want = {(1.0, 2.0)}
        groups = {('filled', 'capped'): {(1.0, 2.0)}, ('none', 'none'): {(3.0, 4.0)}}
        for required in (False, True):
            self.assertTrue(ef.filled_vias_seen(want, groups, required))
            self.assertFalse(ef.filled_vias_seen(want, {('none', 'none'): want | {(5.0, 5.0)}}, required))
            self.assertTrue(ef.filled_vias_found([], [{'x': 1.0}], required))
            self.assertFalse(ef.filled_vias_found(['(1.0, 2.0) 0 matches'], [{'x': 1.0}], required))


class NamesTest(unittest.TestCase):
    def test_upload_base_has_no_dots(self):
        self.assertEqual(ef.upload_base('myboard_v1.2.3'), 'myboard_v1_2_3')
        self.assertEqual(ef.upload_base('plain'), 'plain')

    def test_fab_layer_stem(self):
        self.assertEqual(ef.fab_layer_stem('myboard-L3 (+Sig2).gbr', 'myboard'), 'L3_Sig2')
        self.assertEqual(ef.fab_layer_stem('myboard-F_Cu.gbr', 'myboard'), 'F_Cu')
        self.assertEqual(ef.fab_layer_stem('myboard-Edge_Cuts.gm1', 'myboard'), 'Edge_Cuts')
        self.assertEqual(ef.fab_layer_stem('other-B.Mask.gbr', 'myboard'), 'other_B_Mask')

    def test_copper_extensions(self):
        self.assertEqual(ef.copper_upload_ext(1, 'Top', 'Positive'), 'GTL')
        self.assertEqual(ef.copper_upload_ext(6, 'Bot', 'Positive'), 'GBL')
        self.assertEqual(ef.copper_upload_ext(3, 'Inr', 'Positive'), 'G3L')
        self.assertEqual(ef.copper_upload_ext(4, 'Inr', 'Negative'), 'G4P')

    def test_natural_key(self):
        self.assertEqual(sorted(['C10', 'C2', 'C1', 'R1'], key=ef.natural_key), ['C1', 'C2', 'C10', 'R1'])

    def test_non_copper_layer_table(self):
        exts = sorted(v[1] for v in ef.NON_COPPER.values())
        self.assertEqual(exts, ['BOR', 'GBO', 'GBP', 'GBS', 'GTO', 'GTP', 'GTS'])


class GerberTest(TmpDirTest):
    def test_gerber_objects(self):
        g = ef.gerber_objects(write(os.path.join(self.tmp, 'a.gbr'), GERBER))
        self.assertEqual(g['apertures'][10], ('C', [0.1]))
        self.assertEqual(g['apertures'][11], ('R', [1.0, 2.0]))
        self.assertEqual(g['draws'], [(1.0, -2.0, 3.0, -2.0, 10, 'D')])
        self.assertEqual(g['flashes'], [(5.0, -5.0, 11, 'D'), (6.0, -6.0, 11, 'C')])
        self.assertEqual(len(g['regions']), 1)
        pts, pol = g['regions'][0]
        self.assertEqual(pol, 'D')
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertIn((1.0, 1.0), pts)

    def test_gerber_ops_extents_and_arcs(self):
        flashes, pts = ef.gerber_ops(write(os.path.join(self.tmp, 'a.gbr'), GERBER))
        self.assertEqual(flashes, [(5.0, -5.0), (6.0, -6.0)])
        self.assertIn((3.0, -2.0), pts)
        arc = ('%FSLAX46Y46*%\n%MOMM*%\nG01*\nX1000000Y0D02*\n'
               'G03X-1000000Y0I-1000000J0D01*\nG02X1000000Y0I1000000J0D01*\nM02*\n')
        _, pts = ef.gerber_ops(write(os.path.join(self.tmp, 'arc.gbr'), arc))
        ys = [p[1] for p in pts]
        self.assertAlmostEqual(max(ys), 1.0)    # CCW half circle through (0, 1)
        # the CW arc from (-1, 0) back to (1, 0) about (0, 0) passes (0, 1) as well: no point below y = 0
        self.assertGreaterEqual(min(ys), -1e-9)
        arc_cw = arc.replace('G03X-1000000Y0I-1000000J0D01*\nG02X1000000Y0I1000000J0D01*',
                             'G02X-1000000Y0I-1000000J0D01*')
        _, pts = ef.gerber_ops(write(os.path.join(self.tmp, 'arc_cw.gbr'), arc_cw))
        self.assertAlmostEqual(min(p[1] for p in pts), -1.0)   # CW half circle through (0, -1)

    def test_inch_units(self):
        g = '%FSLAX46Y46*%\n%MOIN*%\nD10*\nX1000000Y1000000D03*\nM02*\n'
        flashes, _ = ef.gerber_ops(write(os.path.join(self.tmp, 'in.gbr'), g))
        self.assertAlmostEqual(flashes[0][0], 25.4)

    def test_x2_attribute_lines(self):
        p = write(os.path.join(self.tmp, 'x2.gbr'), '%TF.FileFunction,Copper,L1,Top*%\n%TA.AperFunction,SMDPad*%\n'
                                                    'G04 comment*\n%TD*%\n%MOMM*%\n')
        self.assertEqual(ef.x2_attribute_lines(p), 3)
        self.assertEqual(ef.x2_attribute_lines(write(os.path.join(self.tmp, 'a.gbr'), GERBER)), 0)

    def test_date_line_filter(self):
        lines = GERBER.splitlines()
        kept = [l for l in lines if not ef.DATE_LINE_RE.search(l)]
        self.assertEqual(len(lines) - len(kept), 1)


class ExcellonTest(TmpDirTest):
    def test_parse(self):
        ex = ef.Excellon(write(os.path.join(self.tmp, 'a.drl'), EXCELLON))
        self.assertEqual(ex.pre[0], 'M48')
        self.assertIn('METRIC', ex.pre)
        self.assertEqual(list(ex.tools), [1, 2])
        self.assertEqual(ex.tools[1]['dia'], 0.3)
        self.assertEqual(ex.tools[1]['lines'][0], '; #@! TA.AperFunction,Plated,PTH,ViaDrill')
        self.assertEqual([(t, xy) for t, xy, _ in ex.hits()], [(1, (10.0, -5.0)), (1, (12.0, -5.0)), (2, (20.0, -8.0))])
        self.assertEqual(ex.body_pre, ['G90', 'G05'])
        self.assertEqual(ex.tail, ['M30'])
        self.assertEqual(ex.slot_lines, [])
        self.assertEqual(ex.eol, '\n')

    def test_split_round_trip_keeps_crlf(self):
        src = write(os.path.join(self.tmp, 'a.drl'), EXCELLON, newline='\r\n')
        ex = ef.Excellon(src)
        self.assertEqual(ex.eol, '\r\n')
        keep = {t: [ln for _, ln in d['hits']] for t, d in ex.tools.items()}
        moved = {1: [keep[1].pop(0)]}
        a, b = os.path.join(self.tmp, 'keep.drl'), os.path.join(self.tmp, 'moved.drl')
        ex.write(a, keep, 'note A')
        ex.write(b, moved, 'note B')
        A, B = ef.Excellon(a), ef.Excellon(b)
        self.assertEqual([xy for _, xy, _ in A.hits()], [(12.0, -5.0), (20.0, -8.0)])
        self.assertEqual([xy for _, xy, _ in B.hits()], [(10.0, -5.0)])
        self.assertEqual(list(B.tools.keys()), [1])          # unused tools are dropped from the header
        with open(b, 'rb') as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b'M48\r\n; note B\r\n'))
        self.assertTrue(raw.endswith(b'M30\r\n'))

    def test_slots_and_errors(self):
        slot = EXCELLON.replace('X20.0Y-8.0', 'G00X20.0Y-8.0\nM15\nG01X21.0Y-8.0\nM16')
        ex = ef.Excellon(write(os.path.join(self.tmp, 's.drl'), slot))
        self.assertTrue(ex.slot_lines)
        with self.assertRaises(ef.StepError):
            ef.Excellon(write(os.path.join(self.tmp, 'bad.drl'), EXCELLON.replace('%\n', '')))
        with self.assertRaises(ef.StepError):
            ef.Excellon(write(os.path.join(self.tmp, 'bad2.drl'), EXCELLON.replace('T1\nX10', 'X10')))


class BoardTextTest(unittest.TestCase):
    def test_board_vias_text_defaults_from_setup(self):
        vias = ef.board_vias_text(BOARD_VIAS)
        self.assertEqual(len(vias), 2)
        v1, v2 = vias
        self.assertEqual((v1['x'], v1['y'], v1['drill']), (10.0, 5.0, 0.3))
        self.assertTrue(v1['filled'])            # explicit
        self.assertTrue(v1['capped'])            # from (setup (capping yes))
        self.assertEqual(v1['kind'], '')
        self.assertEqual(v1['layers'], '"F.Cu" "B.Cu"')
        self.assertFalse(v2['filled'])           # no token, setup has no (filling yes)
        self.assertFalse(v2['capped'])           # explicit no beats the setup default
        self.assertEqual(v2['kind'], 'blind')


class PasteTest(unittest.TestCase):
    def test_paste_findings(self):
        fps = {
            'C1': {'pad_box_mm': [0, 0, 1, 1], 'paste_pads': [], 'paste_graphics': []},
            'C2': {'pad_box_mm': [5, 0, 6, 1], 'paste_pads': [], 'paste_graphics': []},
            'R1': {'pad_box_mm': [2, 0, 3, 1], 'paste_pads': [['1', 'F.Paste']], 'paste_graphics': []},
            'U1': {'pad_box_mm': [0, 0, 4, 4], 'paste_pads': [],
                   'paste_graphics': [{'class': 'PCB_SHAPE', 'layer': 'B.Paste', 'uuid': 'u-1',
                                       'bbox_mm': [1, 1, 3, 3]}]},
            'J1': {'pad_box_mm': [8, 0, 9, 1], 'paste_pads': [], 'paste_graphics': []},
        }
        rows = [{'ref': 'C1', 'side': 1, 'pop': 1, 'type': 1}, {'ref': 'C2', 'side': 1, 'pop': 1, 'type': 1},
                {'ref': 'R1', 'side': 1, 'pop': 0, 'type': 1}, {'ref': 'U1', 'side': 2, 'pop': 0, 'type': 1},
                {'ref': 'J1', 'side': 1, 'pop': 1, 'type': 2}]
        paste = {'F': {'flashes': [(0.5, -0.5, 10, 'D'), (2.5, -0.5, 10, 'D'), (5.5, -0.5, 10, 'C')],
                       'regions': [], 'draws': []},
                 'B': {'flashes': [], 'regions': [([(1, -1), (3, -1), (3, -3)], 'D')], 'draws': []}}
        source, plotted, unpasted = ef.paste_findings(fps, rows, paste)
        self.assertEqual(list(source), ['R1', 'U1'])
        self.assertIn('1 pad on a paste layer (1 F.Paste)', source['R1'][0])
        self.assertIn('uuid u-1', source['U1'][0])
        self.assertEqual(dict(plotted['R1']), {'flash': 1})
        self.assertEqual(dict(plotted['U1']), {'region': 1})
        self.assertEqual(unpasted, ['C2'])        # its only flash is clear polarity; J1 is through-hole


def lz_compress_b64(s):
    """LZString.compressToBase64, ported for the round-trip test of export_fab.lz_decompress_b64. A Python port of
    lz-string's compressor (lz-string: MIT License, Copyright (c) 2013 pieroxy,
    https://github.com/pieroxy/lz-string)."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
    bits_per_char = 6
    st = {'val': 0, 'pos': 0}
    data = []

    def put(value, nbits):
        for _ in range(nbits):
            st['val'] = (st['val'] << 1) | (value & 1)
            if st['pos'] == bits_per_char - 1:
                st['pos'] = 0
                data.append(alphabet[st['val']])
                st['val'] = 0
            else:
                st['pos'] += 1
            value >>= 1

    dictionary, to_create = {}, set()
    w, enlarge, dict_size, num_bits = '', 2, 3, 2

    def emit_w():
        nonlocal enlarge, num_bits
        if w in to_create:
            if ord(w[0]) < 256:
                put(0, num_bits)
                put(ord(w[0]), 8)
            else:
                put(1, num_bits)
                put(ord(w[0]), 16)
            enlarge -= 1
            if enlarge == 0:
                enlarge, num_bits = 1 << num_bits, num_bits + 1
            to_create.discard(w)
        else:
            put(dictionary[w], num_bits)
        enlarge -= 1
        if enlarge == 0:
            enlarge, num_bits = 1 << num_bits, num_bits + 1

    for c in s:
        if c not in dictionary:
            dictionary[c] = dict_size
            dict_size += 1
            to_create.add(c)
        wc = w + c
        if wc in dictionary:
            w = wc
        else:
            emit_w()
            dictionary[wc] = dict_size
            dict_size += 1
            w = c
    if w:
        emit_w()
    put(2, num_bits)
    while True:
        st['val'] <<= 1
        if st['pos'] == bits_per_char - 1:
            data.append(alphabet[st['val']])
            break
        st['pos'] += 1
    res = ''.join(data)
    return res + '=' * ((4 - len(res) % 4) % 4)


class LzStringTest(unittest.TestCase):
    def test_round_trip(self):
        samples = ['a', 'hello hello hello', 'abababababababababab', json.dumps({'bom': {'F': [[['C1', 1]]]},
                                                                               'metadata': {'revision': '1.0'}}),
                   'unicode µF Ω 中文', ''.join(chr(32 + (i * 7) % 90) for i in range(3000))]
        for s in samples:
            self.assertEqual(ef.lz_decompress_b64(lz_compress_b64(s)), s, s[:20])

    def test_empty(self):
        self.assertEqual(ef.lz_decompress_b64(''), '')


class CtxTest(TmpDirTest):
    def test_short_tags_paths_with_forward_slashes(self):
        C = ef.Ctx(argparse.Namespace(ibom_pkg=None))
        C.work = os.path.join(self.tmp, 'work')
        C.out = os.path.join(self.tmp, 'out')
        C.top = os.path.join(self.tmp, 'repo')
        s = C.short('%s and %s and %s' % (os.path.join(C.work, 'a', 'b.txt'), os.path.join(C.out, 'fab'), C.top))
        self.assertEqual(s, '<work>/a/b.txt and <out>/fab and <repo>')
        self.assertEqual(C.short(ef.__file__), '<export_fab.py>')
        p = C.portable({'k': [os.path.join(C.out, 'x')]})
        self.assertEqual(p['k'], ['<out>/x'])

    def test_short_repo_wins_when_it_is_the_main_checkout(self):
        C = ef.Ctx(argparse.Namespace(ibom_pkg=None))
        C.top = C.main_checkout = os.path.join(self.tmp, 'repo')
        C.out = os.path.join(self.tmp, 'repo', 'out')
        text = '%s %s' % (os.path.join(C.top, 'hw', 'b.kicad_pcb'), os.path.join(C.out, 'x'))
        for _ in range(5):      # no dependence on set or hash order
            self.assertEqual(C.short(text), '<repo>/hw/b.kicad_pcb <out>/x')
        C.main_checkout = self.tmp                              # a linked worktree inside the main checkout
        self.assertEqual(C.short(os.path.join(self.tmp, 'other', 'f')), '<main-checkout>/other/f')
        self.assertEqual(C.short(os.path.join(C.top, 'f')), '<repo>/f')

    def test_check_and_quote(self):
        C = ef.Ctx(argparse.Namespace())
        self.assertTrue(C.check('a', True))
        self.assertFalse(C.check('b', False, 'why', level='warn'))
        self.assertEqual([c['level'] for c in C.checks], ['error', 'warn'])
        self.assertEqual(ef._q('a b'), '"a b"')
        self.assertEqual(ef._q(''), '""')
        self.assertEqual(ef._q('ab'), 'ab')

    def test_printed_text(self):
        self.assertEqual(ef.check_line({'name': 'zip ok', 'level': 'error', 'ok': True, 'detail': 'x'}), 'ok    zip ok')
        self.assertEqual(ef.check_line({'name': 'n', 'level': 'warn', 'ok': False, 'detail': ''}), 'WARN  n')
        self.assertEqual(ef.check_line({'name': 'n', 'level': 'error', 'ok': False, 'detail': 'why'}),
                         'FAIL  n - why')
        self.assertEqual((ef.plural(1, 'Populate 0 part'), ef.plural(2, 'page'), ef.plural(0, 'part')),
                         ('1 Populate 0 part', '2 pages', '0 parts'))
        self.assertEqual(ef.config.show_path(os.path.join('fab', 'x.txt')), 'fab/x.txt')


class UploadZipTest(TmpDirTest):
    def make_package(self, name='board_v1.0', xlsx=False):
        out = self.tmp
        base = ef.upload_base(name)
        layer_map = [{'fab_file': '%s_F_Cu.gbr' % name, 'upload_file': '%s.GTL' % base},
                     {'fab_file': '%s_Edge_Cuts.gbr' % name, 'upload_file': '%s.BOR' % base}]
        for s in layer_map:
            write(os.path.join(out, 'fab', s['fab_file']), 'G04 %s*\nM02*\n' % s['fab_file'])
        for kind in ('PTH', 'PTH_FILLED', 'NPTH'):
            write(os.path.join(out, 'fab', '%s_%s.drl' % (name, kind)), 'M48\n%\nM30\n')
        write(os.path.join(out, 'assembly', '%s.XYRS' % name),
              '# header\nC1\t1.00\t2.00\t0\t1\t1\t10.00\t20.00\t10k\tR_0603\t1\tMPN1\n'
              'C2\t3.00\t4.00\t90\t2\t1\t10.00\t20.00\t10k\tR_0603\t0\tMPN1\n')
        if xlsx:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(['Designator', 'Value', 'Footprint', 'Populate', 'MPN', 'Manufacturer'])
            ws.append(['C1', '10k', 'R_0603', 1, 'MPN1', 'M'])
            ws.append(['C2', '10k', 'R_0603', 0, 'MPN1', 'M'])
            os.makedirs(os.path.join(out, 'bom'))
            wb.save(os.path.join(out, 'bom', '%s_macrofab.xlsx' % name))
        return {'name': name, 'upload_base': base, 'layer_map': layer_map, 'commit_date': '2026-01-02T03:04:06+00:00'}

    def test_upload_members_order_and_names(self):
        m = self.make_package()
        members = ef.upload_members(self.tmp, m['name'], m['layer_map'])
        self.assertEqual([arc for _, arc in members], ['board_v1_0.GTL', 'board_v1_0.BOR', 'board_v1_0_PTH.XLN',
                                                       'board_v1_0_PTH_FILLED.XLN', 'board_v1_0_NPTH.XLN',
                                                       'board_v1_0.XYRS'])

    def test_build_zip_is_flat_dated_and_byte_identical(self):
        m = self.make_package()
        C = ef.Ctx(argparse.Namespace())
        C.out = self.tmp
        out, names = ef.build_zip(C, m)
        self.assertEqual(os.path.basename(out), 'board_v1.0_macrofab_upload.zip')
        self.assertTrue(all(n.count('.') == 1 for n in names))
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.getinfo('board_v1_0.XYRS').date_time, (2026, 1, 2, 3, 4, 6))
        failed = [c for c in C.checks if not c['ok'] and c['level'] == 'error']
        self.assertEqual(failed, [])
        self.assertTrue(any('no bom' in c['name'] for c in C.checks if c['level'] == 'warn'))
        with open(out, 'rb') as f:
            first = f.read()
        os.remove(out)
        ef.build_zip(C, m)
        with open(out, 'rb') as f:
            self.assertEqual(f.read(), first)       # reproducible: fixed member dates and order

    def test_build_zip_accepts_a_utc_z_commit_date(self):
        m = self.make_package()
        m['commit_date'] = '2026-01-02T03:04:06Z'        # git's %cI for a UTC commit; Python < 3.11 rejects 'Z'
        C = ef.Ctx(argparse.Namespace())
        C.out = self.tmp
        out, _ = ef.build_zip(C, m)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.getinfo('board_v1_0.XYRS').date_time, (2026, 1, 2, 3, 4, 6))

    def test_build_zip_with_xlsx_checks_designators(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest('openpyxl not installed')
        m = self.make_package(xlsx=True)
        C = ef.Ctx(argparse.Namespace())
        C.out = self.tmp
        out, names = ef.build_zip(C, m)
        self.assertIn('board_v1_0_macrofab.xlsx', names)
        self.assertTrue(all(c['ok'] for c in C.checks if c['name'].startswith('xlsx vs XYRS')))
        # a designator mismatch stops the zip
        xyrs = os.path.join(self.tmp, 'assembly', 'board_v1.0.XYRS')
        with open(xyrs, 'a', encoding='ascii', newline='\n') as f:
            f.write('C3\t5.00\t6.00\t0\t1\t1\t1.00\t1.00\t1u\tC_0402\t1\tMPN2\n')
        C2 = ef.Ctx(argparse.Namespace())
        C2.out = self.tmp
        with self.assertRaises(ef.StepError):
            ef.build_zip(C2, m)

    def test_zip_only_setup_errors_exit_2(self):
        mpath = os.path.join(self.tmp, 'docs', 'board_v1.0_export_manifest.json')
        for manifest, why in ((None, 'needs exactly one docs/*_export_manifest.json'),
                              ('{', 'is not a kicad-fab-export manifest'),
                              ('{"name": "board_v1.0"}', "no 'layer_map' key")):
            if manifest is not None:
                write(mpath, manifest)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(ef.main(['--zip-only', '--out', self.tmp]), 2)
            self.assertTrue(out.getvalue().startswith('ERROR: '), out.getvalue())
            self.assertIn(why, out.getvalue())

    def test_zip_only_prints_clean_check_lines(self):
        m = self.make_package()
        m.update({'checks': [], 'outputs': []})
        write(os.path.join(self.tmp, 'docs', 'board_v1.0_export_manifest.json'), json.dumps(m))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ef.main(['--zip-only', '--out', self.tmp]), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual([l for l in lines if l != l.rstrip()], [])            # no trailing spaces
        self.assertIn('WARN  upload zip: no bom/board_v1.0_macrofab.xlsx yet (run kicad-macrofab-bom, then '
                      'kicad-fab-export --zip-only)', lines)
        self.assertTrue(lines[-1].startswith('wrote ') and '\\' not in lines[-1], lines[-1])

    def test_file_tables(self):
        self.make_package()
        C = ef.Ctx(argparse.Namespace())
        C.out = self.tmp
        mpath = write(os.path.join(self.tmp, 'docs', 'board_v1.0_export_manifest.json'), '{}')
        write(os.path.join(self.tmp, 'README.md'), 'hello')
        outs, other = ef.package_tables(C, mpath, ['assembly/board_v1.0.XYRS'])
        self.assertEqual([r['path'] for r in outs], ['assembly/board_v1.0.XYRS'])
        self.assertIn('README.md', [r['path'] for r in other])
        self.assertNotIn('docs/board_v1.0_export_manifest.json', [r['path'] for r in other])
        self.assertEqual(len(outs[0]['sha256']), 64)


class _FakePage:
    def __init__(self, words):
        self.words = words

    def get_text(self, kind):
        assert kind == 'words'
        return [(0, 0, 1, 1, w, 0, 0, i) for i, w in enumerate(self.words)]


class _FakeDoc:
    def __init__(self, path):
        with open(path, encoding='ascii') as f:
            self.pages = [_FakePage(line.split()) for line in f.read().splitlines()[1:]]
        self.page_count = len(self.pages)

    def __getitem__(self, i):
        return self.pages[i]

    def close(self):
        pass


class AssemblyPdfTest(TmpDirTest):
    """step_assembly_pdf without pypdf: two one-page files, and the designator check still runs on them."""

    def ctx(self, printed):
        C = ef.Ctx(argparse.Namespace())
        C.out, C.work, C.prefix, C.board = self.tmp, self.tmp, 'board_v1.0', 'board.kicad_pcb'
        os.makedirs(os.path.join(self.tmp, 'assembly'))     # main() creates fab/, assembly/ and docs/
        C.xyrs_rows = [{'ref': 'R1', 'side': 1}, {'ref': 'C1', 'side': 1}, {'ref': 'JP1', 'side': 2}]

        def kcli(*args):        # a stand-in "PDF" per side: a header line, then the words printed on the page
            layer = args[args.index('-l') + 1].split(',')[0]
            write(args[args.index('-o') + 1], '%%PDF-1.4\n%s\n' % ' '.join(printed[layer]))
            return ''
        C.kcli = kcli
        return C

    def run_step(self, printed, pymupdf=True):
        fake = types.ModuleType('pymupdf')
        fake.open = _FakeDoc
        mods = {'pypdf': None, 'pymupdf': fake if pymupdf else None, 'fitz': None}
        C = self.ctx(printed)
        with mock.patch.dict(sys.modules, mods):
            detail = ef.step_assembly_pdf(C)
        return C, detail

    def test_no_pypdf_still_checks_designators(self):
        C, detail = self.run_step({'F.Fab': ['R1', 'C1', 'Title'], 'B.Fab': ['JP1']})
        for side in ('top', 'bottom'):
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'assembly', 'board_v1.0_assembly_%s.pdf' % side)))
        by_name = {c['name']: c for c in C.checks}
        self.assertFalse(by_name['assembly PDF: pypdf missing, written as two files']['ok'])
        self.assertTrue(by_name["assembly PDF: every XYRS designator is printed on its side's page (3)"]['ok'])
        self.assertEqual(detail, 'two files (no pypdf), all 3 designators found')

    def test_no_pypdf_missing_designator_fails(self):
        C, detail = self.run_step({'F.Fab': ['R1', 'JP1'], 'B.Fab': ['C1']})
        c = [c for c in C.checks if c['name'].startswith('assembly PDF: every XYRS designator')][0]
        self.assertEqual((c['ok'], c['level'], c['detail']), (False, 'error', 'missing C1 JP1'))
        self.assertTrue(detail.endswith(', 2 missing'))

    def test_no_pypdf_no_pymupdf_warns_twice(self):
        C, detail = self.run_step({'F.Fab': ['R1', 'C1'], 'B.Fab': ['JP1']}, pymupdf=False)
        self.assertEqual([(c['name'], c['level'], c['ok']) for c in C.checks],
                         [('assembly PDF: pypdf missing, written as two files', 'warn', False),
                          ('assembly PDF: designators not checked (no PyMuPDF)', 'warn', False)])
        self.assertEqual(detail, 'two files (no pypdf)')


class ExpectKeysTest(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(collections.Counter(ef.EXPECT_KEYS)['fitted'], 1)
        self.assertIn('filled', ef.EXPECT_KEYS)


if __name__ == '__main__':
    unittest.main()
