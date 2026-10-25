import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from kicad_fab_package import __main__ as cli_main
from kicad_fab_package import bom_check, bomdiff, config, export_fab, make_macrofab_xlsx

from ._util import rmtree


def write_csv(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


class BomdiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kfp_bomdiff_')

    def tearDown(self):
        rmtree(self.tmp)

    def test_compare_with_tempco_alias_and_missing_columns(self):
        a = write_csv(os.path.join(self.tmp, 'a.csv'), ['Reference', 'Value', 'Footprint', 'MPN', 'Tempco', 'DNP'],
                      [['C1', '1u', 'C_0402', 'X', 'X7R', ''], ['R1', '1k', 'R_0603', 'Y', '', ''],
                       ['R2', '2k', 'R_0603', 'Z', '', '']])
        b = write_csv(os.path.join(self.tmp, 'b.csv'), ['Reference', 'Value', 'Footprint', 'MPN', 'Manufacturer',
                                                        'TempCo', 'DNP'],
                      [['C1', '1u', 'C_0402', 'X', 'Murata', 'X5R', ''], ['R1', '1k', 'R_0603', 'Y2', 'Yageo', '', ''],
                       ['R10', '10k', 'R_0603', 'W', 'Yageo', '', 'DNP']])
        (ra, ca), (rb, cb) = bomdiff.load(a), bomdiff.load(b)
        self.assertIn('TempCo', ca)
        c = bomdiff.compare(ra, ca, rb, cb)
        self.assertEqual(c['only_b'], ['Manufacturer'])
        self.assertEqual(c['added'], ['R10'])
        self.assertEqual(c['removed'], ['R2'])
        self.assertEqual(c['changed'], [('C1', [('TempCo', 'X7R', 'X5R')]), ('R1', [('MPN', 'Y', 'Y2')])])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(bomdiff.main([a, b]), 0)
        text = out.getvalue()
        self.assertIn('NOTE: not compared, column missing on one side: only in B: Manufacturer', text)
        self.assertIn('ADDED (1):', text)
        self.assertIn("~ R1     MPN: 'Y' -> 'Y2'", text)
        self.assertEqual([l for l in text.splitlines() if l != l.rstrip()], [])      # no trailing spaces

    def test_unreadable_inputs_are_setup_errors(self):
        good = write_csv(os.path.join(self.tmp, 'good.csv'), ['Reference', 'Value'], [['R1', '1k']])
        no_ref = write_csv(os.path.join(self.tmp, 'no_ref.csv'), ['Ref', 'Qty', 'Value'], [['R1,R2', '2', '1k']])
        grouped = write_csv(os.path.join(self.tmp, 'grouped.csv'), ['Reference', 'Qty', 'Value'],
                            [['R1', '1', '2k'], ['R2,R3', '2', '1k']])
        empty = os.path.join(self.tmp, 'empty.csv')
        open(empty, 'w').close()
        latin1 = os.path.join(self.tmp, 'latin1.csv')
        with open(latin1, 'wb') as f:
            f.write(b'Reference,Value\nR1,10\xb5F\n')
        cases = [(os.path.join(self.tmp, 'nope.csv'), 'file not found'),
                 (no_ref, 'no Reference column (columns: Ref, Qty, Value)'),
                 (grouped, "a grouped BOM (Reference 'R2,R3'); kicad-bomdiff reads per-reference csvs"),
                 (empty, 'no Reference column (columns: none, the file is empty)'),
                 (latin1, 'not a UTF-8 csv')]
        for path, why in cases:
            for argv in ([path, good], [good, path]):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(bomdiff.main(argv), 2, argv)
                self.assertTrue(out.getvalue().startswith('ERROR: %s: ' % path), out.getvalue())
                self.assertIn(why, out.getvalue())

    def test_usage(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(bomdiff.main([]), 2)
            self.assertEqual(bomdiff.main(['--help']), 0)

    def test_sortkey(self):
        self.assertEqual(sorted(['R10', 'R2', 'C1'], key=bomdiff.sortkey), ['C1', 'R2', 'R10'])


class BomCheckTest(unittest.TestCase):
    def test_recipes(self):
        self.assertEqual(bom_check.GROUPED[0], '--fields')
        self.assertIn('${DNP}', bom_check.GROUPED[1])
        self.assertEqual(bom_check.PERREF[-1], '')            # --group-by '' : one line per reference

    def test_needs_a_csv_to_compare_with(self):
        tmp = tempfile.mkdtemp(prefix='kfp_bomcheck_')
        try:
            out = io.StringIO()
            with mock.patch.dict(os.environ, {config.CONFIG_ENV: ''}), redirect_stdout(out):
                rc = bom_check.main(['HEAD', '--repo', tmp])
            self.assertEqual(rc, 2)
            self.assertIn('no BOM csv to compare with', out.getvalue())
        finally:
            rmtree(tmp)


class SharedRulesTest(unittest.TestCase):
    def test_xyrs_and_bom_use_the_same_non_part_rule(self):
        self.assertEqual(export_fab.NON_PART_RE.pattern, make_macrofab_xlsx.NON_PART_RE.pattern)
        self.assertEqual(export_fab.NON_PART_LIBS, make_macrofab_xlsx.NON_PART_LIBS)
        self.assertEqual(config.NON_PART_REFS, export_fab.NON_PART_RE.pattern)      # the settings' defaults
        self.assertEqual(tuple(config.NON_PART_LIBS), export_fab.NON_PART_LIBS)
        self.assertTrue(export_fab.is_non_part('FID2', 'Anything:X'))
        self.assertTrue(export_fab.is_non_part('P101', 'MountingHole:MountingHole_3.2mm_M3'))
        self.assertFalse(export_fab.is_non_part('J1', 'Connector:Conn_01x02'))
        self.assertFalse(export_fab.is_non_part('J1', 'MountingHole'))      # no library prefix


class EntryPointTest(unittest.TestCase):
    def test_dispatcher_lists_commands(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli_main.main([]), 0)
            self.assertEqual(cli_main.main(['nope']), 2)
        self.assertIn('kicad-fab-export', out.getvalue())

    def test_help_of_every_tool(self):
        for mod in (export_fab, make_macrofab_xlsx, bom_check):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as e:
                mod.main(['--help'])
            self.assertEqual(e.exception.code, 0)


if __name__ == '__main__':
    unittest.main()
