"""Consistency checks between the documentation, the tools' own text and the demo outputs the docs quote (no KiCad
needed)."""
import collections
import os
import re
import unittest

from kicad_fab_package import __version__
from kicad_fab_package import make_macrofab_xlsx as mx

from .test_macrofab_bom import design

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE_DOCS = os.path.isfile(os.path.join(ROOT, 'docs', 'macrofab.md'))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def flat(text):
    """Markdown text with its line breaks and indentation collapsed to single spaces."""
    return re.sub(r'\s+', ' ', text)


def section(text, title):
    """The body of the '## ' section titled title, up to the next '## ' heading."""
    m = re.search(r'^## %s\n(.*?)(?=^## |\Z)' % re.escape(title), text, re.M | re.S)
    if not m:
        raise AssertionError('no section %r' % title)
    return m.group(1)


def refs_of(text):
    """'`R1`-`R4`, `R6`' -> {'R1', 'R2', 'R3', 'R4', 'R6'}"""
    out = set()
    for a, b in re.findall(r'`([A-Z]+\d+)`(?:-`([A-Z]+\d+)`)?', text):
        out |= mx.expand_refs('%s-%s' % (a, b) if b else a)
    return out


def checks_report():
    """A checks report with a collision and a mixed-Populate group, from the synthetic design of the BOM tests."""
    bom, comps, fps = design()
    rows, res = mx.build_rows(bom, comps, [], fps)
    return mx.checks_md('board_v1.2', 'commit `abc`', '10.0.7', ['kicad-cli ...'], rows, res, mx.hygiene(rows), [],
                        refs=['x'])


RELEASE_HEADING = re.compile(r'^## \[(\d[^\]]*)\]', re.M)     # '## [0.1.0] - ...', not '## [Unreleased]'


def newest_release_entry(changelog, version):
    """The CHANGELOG text after the newest release heading (the older entries below it included), or None when that
    heading is not version. Only the newest heading is compared: every release keeps the entries before it."""
    if RELEASE_HEADING.findall(changelog)[:1] != [version]:
        return None
    return flat(changelog.split('## [%s]' % version, 1)[1])


def with_release(changelog, version):
    """changelog with a routine release entry for version added above the newest one, as the next release adds it."""
    at = RELEASE_HEADING.search(changelog).start()
    return '%s## [%s] - 2099-01-01\n\n### Fixed\n\n- A fix.\n\n%s' % (changelog[:at], version, changelog[at:])


@unittest.skipUnless(HAVE_DOCS, 'docs/ not present')
class BomDocsTest(unittest.TestCase):
    def test_bom_docs_state_no_grouping_rule_and_quote_the_report(self):
        bom = read('docs', 'bom.md')
        for claim in ('groups BOM lines by', 'Ungroup', 'New Group', 'merged the line'):
            self.assertFalse(claim in bom, 'docs/bom.md still says %r' % claim)
        report = checks_report()
        # the advice lines and section headings bom.md quotes from the demo's reports are the tool's own text
        quoted = [l for l in bom.splitlines() if l.startswith('After the import')]
        self.assertEqual(sorted(quoted), sorted(l for l in report.splitlines() if l.startswith('After the import')))
        uncount = re.compile(r' \(\d+\)$')
        headings = {uncount.sub('', l) for l in report.splitlines() if l.startswith('### ')}
        for l in bom.splitlines():
            if l.startswith('### Value + footprint') or l.startswith('### MPNs with'):
                self.assertIn(uncount.sub('', l), headings)

    def test_report_points_at_the_walkthrough_section(self):
        self.assertIn('"Line grouping and Populate", section 7 of the MacroFab walkthrough, docs/macrofab.md',
                      mx.LINE_GROUPING)
        self.assertRegex(read('docs', 'macrofab.md'), r'(?m)^## 7\. Line grouping and Populate$')

    def test_xlsx_writer_switch_is_documented(self):
        self.assertIn('| `OPENPYXL_LXML` | BOM |', section(read('docs', 'cli.md'), 'Environment variables'))
        self.assertIn('`OPENPYXL_LXML=False`', flat(read('docs', 'bom.md')))


@unittest.skipUnless(HAVE_DOCS, 'docs/ not present')
class MacroFabWalkthroughTest(unittest.TestCase):
    def setUp(self):
        self.text = read('docs', 'macrofab.md')

    def test_collision_example_matches_the_report(self):
        # the demo's v1.1 report row, as docs/bom.md quotes it: DEMO-R-10K: R1-R4, R6-R7; DEMO-R-10K-1PCT: R5
        rows = re.findall(r'^\| 10K \| \S+ \| (.*) \|$', read('docs', 'bom.md'), re.M)
        self.assertEqual(len(rows), 1)
        report = {mpn: mx.expand_refs(refs) for mpn, refs in (p.split(': ') for p in rows[0].split('; '))}
        self.assertEqual(report['DEMO-R-10K-1PCT'], {'R5'})
        bullet = flat(section(self.text, '7. Line grouping and Populate'))
        bullet = bullet.split('**Value + footprint collisions**', 1)[1].split('**Mixed-Populate groups**', 1)[0]
        said = {mpn: refs_of(refs) for refs, mpn in
                re.findall(r'((?:`[A-Z]+\d+`(?:-`[A-Z]+\d+`)?(?:, )?)+) at `([^`]+)`', bullet)}
        self.assertEqual(said, report)

    def test_layer_mapping_rows_are_confirm_files_rows(self):
        sec = section(self.text, '3. Confirm Files: the layer mapping')
        self.assertIn('Check every Gerber and drill row against `fab/NAME_layer_map.csv`:', flat(sec))
        # the upload files of the layer map export-fab.md shows: the Gerbers and the drill files
        layer_map = re.search(r'^order,kicad_layer,.*?\n(.*?)```', read('docs', 'export-fab.md'), re.M | re.S)
        mapped = {re.sub(r'^pic_programmer_v1_0', '', l.rsplit(',', 1)[1]) for l in layer_map.group(1).splitlines()}
        table = {}
        for row in re.findall(r'^\| (`BASE.*?) \|', sec, re.M):
            for name in re.findall(r'`BASE([^`]*)`', row):
                table[name] = row
        inner = {n for n in table if re.match(r'^\.G\d+[LP]$', n)}
        self.assertTrue(mapped <= set(table), mapped - set(table))
        # every other row is a file Confirm Files lists but the layer map does not: the XYRS. The BOM xlsx is taken
        # in the wizard's first step, so it has no row here.
        self.assertEqual(set(table) - mapped - inner, {'.XYRS'})

    def test_each_ui_label_has_one_spelling(self):
        spellings = collections.defaultdict(set)
        for label in re.findall(r'\*\*([^*]+)\*\*', self.text):
            key = ' '.join(w for w in label.lower().split() if w not in ('a', 'an', 'the'))
            spellings[key].add(label)
        self.assertEqual({k: v for k, v in spellings.items() if len(v) > 1}, {})
        self.assertIn('**Add Component**', self.text)         # the label the UI showed

    def test_part_sourcing_sets_me_in_the_same_visit(self):
        # section 9: the Sourcing choice did not survive a reload, so section 11 cannot say "set it first"
        self.assertIn('That choice was not kept when the page was reloaded', flat(section(self.text,
                                                                                          '9. Consigned parts')))
        sourcing = flat(section(self.text, '11. Parts MacroFab cannot source'))
        self.assertIn('to **Me** in the same visit, right before **Request Part Sourcing**', sourcing)
        self.assertIn('check that the review lists only the lines MacroFab should buy', sourcing)
        self.assertNotIn('**Me** first', sourcing)


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, 'CHANGELOG.md')), 'CHANGELOG.md not present')
class ChangelogTest(unittest.TestCase):
    NEXT = '99.0.0'     # a later release than any real one, so the simulated entry never collides with a real heading

    def setUp(self):
        self.text = read('CHANGELOG.md')

    def test_newest_release_entry_describes_this_code(self):
        entry = newest_release_entry(self.text, __version__)
        self.assertIsNotNone(entry, 'the newest release heading in CHANGELOG.md is not [%s]' % __version__)
        # behaviour that landed after the entry was first written (library checkout by folder, lxml-independent xlsx)
        self.assertIn('recognised by comparing folders, not path strings', entry)
        self.assertIn('byte-reproducible with or without lxml installed', entry)

    def test_a_routine_release_keeps_the_check_passing(self):
        # the next release adds its entry above the current one and bumps the version: the older entry stays
        current = RELEASE_HEADING.findall(self.text)[0]
        released = with_release(self.text, self.NEXT)
        self.assertEqual(RELEASE_HEADING.findall(released)[:2], [self.NEXT, current])
        entry = newest_release_entry(released, self.NEXT)
        self.assertIsNotNone(entry, 'a CHANGELOG with an older release below the newest one was rejected')
        self.assertIn('recognised by comparing folders, not path strings', entry)
        self.assertIn('byte-reproducible with or without lxml installed', entry)
        # still a guard: a version bump without its entry, or an entry without the bump
        self.assertIsNone(newest_release_entry(self.text, self.NEXT))
        self.assertIsNone(newest_release_entry(released, current))


if __name__ == '__main__':
    unittest.main()
