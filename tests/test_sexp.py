import os
import tempfile
import unittest

from kicad_fab_package import sexp

BOARD_K9 = '''(kicad_pcb
\t(version 20241229)
\t(generator "pcbnew")
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "/SIG A")
\t(segment
\t\t(start 1 2)
\t\t(end 3 4)
\t\t(width 0.2)
\t\t(layer "F.Cu")
\t\t(net 1)
\t\t(uuid "aaaa-1")
\t)
\t(zone
\t\t(net 2)
\t\t(net_name "/SIG A")
\t\t(attr (teardrop (type padvia)))
\t\t(filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 1 0) (xy 1 1)))
\t\t(uuid "bbbb-2")
\t)
)
'''


class ParseTest(unittest.TestCase):
    def test_parse_top_items_spans_and_uuids(self):
        items = sexp.parse_top(BOARD_K9)
        self.assertEqual([i['head'] for i in items], ['version', 'generator', 'net', 'net', 'net', 'segment', 'zone'])
        seg = items[5]
        self.assertEqual(seg['uuid'], 'aaaa-1')
        self.assertTrue(BOARD_K9[seg['start']:seg['end']].startswith('(segment'))
        self.assertTrue(BOARD_K9[seg['start']:seg['end']].endswith(')'))
        self.assertEqual(items[0]['uuid'], None)

    def test_atoms_keep_quotes(self):
        node, end = sexp.parse_span('(property "Value" "10k" (at 1 2))', 0)
        self.assertEqual(node, ['property', '"Value"', '"10k"', ['at', '1', '2']])
        self.assertEqual(end, len('(property "Value" "10k" (at 1 2))'))

    def test_escaped_quote_and_parens_in_string(self):
        node, _ = sexp.parse_span(r'(a "x \" (y)" b)', 0)
        self.assertEqual(node, ['a', r'"x \" (y)"', 'b'])

    def test_unbalanced(self):
        with self.assertRaises(ValueError):
            sexp.parse_span('(a (b c)', 0)
        with self.assertRaises(ValueError):
            sexp.parse_tree('(a (b', 0)

    def test_parse_tree_spans(self):
        text = '(a (b 1) c)'
        t = sexp.parse_tree(text, 0)
        self.assertEqual((t.start, t.end), (0, len(text)))
        self.assertEqual(t[1], ['b', '1'])
        s, e = t.spans[1]
        self.assertEqual(text[s:e], '(b 1)')
        s, e = t.spans[2]
        self.assertEqual(text[s:e], 'c')

    def test_canon_get_getall_strip(self):
        node, _ = sexp.parse_span('(fp (layer "F.Cu")\n   (property "A" "1") (property "B" "2") (filling yes))', 0)
        self.assertEqual(sexp.canon(node), '(fp (layer "F.Cu") (property "A" "1") (property "B" "2") (filling yes))')
        self.assertEqual(sexp.get(node, 'layer'), ['layer', '"F.Cu"'])
        self.assertIsNone(sexp.get(node, 'missing'))
        self.assertEqual(len(sexp.getall(node, 'property')), 2)
        self.assertEqual(sexp.canon(sexp.strip(node, sexp.K10_ONLY)),
                         '(fp (layer "F.Cu") (property "A" "1") (property "B" "2"))')

    def test_norm_maps_k9_net_numbers_to_names(self):
        items = sexp.parse_top(BOARD_K9)
        nets = {i['node'][1]: i['node'][2] for i in items if i['head'] == 'net'}
        seg = items[5]['node']
        self.assertIn(['net', '"GND"'], sexp.norm(seg, nets))
        # a KiCad 10 by-name reference stays as it is
        self.assertEqual(sexp.norm(['net', '"VCC"'], {}), ['net', '"VCC"'])

    def test_teardrop_and_version(self):
        items = sexp.parse_top(BOARD_K9)
        self.assertTrue(sexp.is_teardrop(items[6]['node']))
        self.assertFalse(sexp.is_teardrop(items[5]['node']))
        self.assertEqual(sexp.board_version(BOARD_K9), 20241229)
        self.assertIsNone(sexp.board_version('(kicad_pcb)'))

    def test_load_board_and_byte_exact_io(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'b.kicad_pcb')
        crlf = BOARD_K9.replace('\n', '\r\n')
        sexp.write_text(p, crlf)
        with open(p, 'rb') as f:
            self.assertEqual(f.read(), crlf.encode('utf-8'))
        text, items, nets = sexp.load_board(p)
        self.assertEqual(text, crlf)
        self.assertEqual(nets['1'], '"GND"')
        self.assertEqual(len(items), 7)
        os.remove(p)
        os.rmdir(d)


if __name__ == '__main__':
    unittest.main()
