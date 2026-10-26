"""End-to-end run on a real KiCad project. Skipped unless KiCad 10 (kicad-cli and its python), git and a project are
available. The project is KiCad's own pic_programmer demo, or the folder named by KFP_TEST_KICAD_PROJECT (one
.kicad_pro in it); it is committed into a scratch git repository first. A second run moves it into a
kicad-project-template layout (hw/demo/ beside the library folder hw/lib/), gives it a round outline and exports the
PCBWay files too. Set KFP_SKIP_INTEGRATION=1 to skip."""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout

from kicad_fab_package import bom_check, config, export_fab, make_macrofab_xlsx

from ._util import rmtree


def find_project():
    given = os.environ.get('KFP_TEST_KICAD_PROJECT')
    if given:
        return given if os.path.isdir(given) else None
    models = config.find_kicad_3dmodel_dir(None, config.find_kicad_cli())
    if not models:
        return None
    for demo in ('pic_programmer', 'interf_u', 'video'):
        p = os.path.join(os.path.dirname(models), 'demos', demo)
        if os.path.isdir(p) and len([f for f in os.listdir(p) if f.endswith('.kicad_pro')]) == 1:
            return p
    return None


def kicad_major(cli):
    try:
        out = subprocess.run([cli, 'version'], capture_output=True, text=True, timeout=60).stdout
        return int(out.strip().split('.')[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


CLI = config.find_kicad_cli()
CLI = CLI if CLI and os.path.isfile(CLI) else None
KPY = config.find_kicad_python(None, CLI) if CLI else None
PROJECT = find_project() if CLI else None
REASON = ('KFP_SKIP_INTEGRATION is set' if os.environ.get('KFP_SKIP_INTEGRATION') else
          'openpyxl not installed' if make_macrofab_xlsx.openpyxl is None else
          'git not found' if not shutil.which('git') else
          'kicad-cli not found' if not CLI else
          'KiCad python not found' if not (KPY and os.path.isfile(KPY)) else
          'KiCad 10 or newer needed' if kicad_major(CLI) < 10 else
          'no KiCad demo project found (set KFP_TEST_KICAD_PROJECT)' if not PROJECT else None)


def git(cwd, *args):
    # a UTC commit date: git prints it as ...Z, which Python before 3.11 cannot parse without help
    when = '2026-01-02T03:04:05+00:00'
    env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(['git', '-C', cwd, '-c', 'user.name=test', '-c', 'user.email=test', '-c', 'commit.gpgsign=false',
                    '-c', 'core.longpaths=true', '-c', 'core.autocrlf=false'] + list(args), check=True,
                   capture_output=True, env=env)


@unittest.skipIf(REASON, REASON or '')
class KiCadIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='kfp_it_')
        cls.repo = os.path.join(cls.tmp, 'repo')
        shutil.copytree(PROJECT, os.path.join(cls.repo, 'hw'))
        git(cls.repo, '-c', 'init.defaultBranch=main', 'init', '-q')
        git(cls.repo, 'add', '-A')
        git(cls.repo, 'commit', '-qm', 'project')
        cls.out = os.path.join(cls.tmp, 'out')
        cls.bom = os.path.join(cls.out, 'bom')
        common = ['--repo', cls.repo, '--name', 'demo_v1', '--kicad-cli', CLI]
        with redirect_stdout(io.StringIO()) as cls.bom_log:
            cls.bom_rc = make_macrofab_xlsx.main(['HEAD', '--out', cls.bom] + common)
        with redirect_stdout(io.StringIO()) as cls.fab_log:
            cls.fab_rc = export_fab.main(['HEAD', '--out', cls.out, '--kicad-python', KPY,
                                          '--work', os.path.join(cls.tmp, 'work')] + common)

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.tmp)

    def test_bom_outputs(self):
        self.assertIn(self.bom_rc, (0, 1), self.bom_log.getvalue()[-2000:])     # 1: the demo has no MPNs
        for suffix in ('_macrofab.xlsx', '_bom.csv', '_bom_perref.csv', '_bom_checks.md'):
            self.assertTrue(os.path.isfile(os.path.join(self.bom, 'demo_v1' + suffix)), suffix)
        self.assertFalse(any(f.startswith('demo_v1_vs_') for f in os.listdir(self.bom)))   # no baseline configured

    def test_every_step_ran(self):
        self.assertIn(self.fab_rc, (0, 1), self.fab_log.getvalue()[-3000:])
        with open(os.path.join(self.out, 'docs', 'demo_v1_export_manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        failed = [s for s in m['steps'] if s[1] == 'FAIL']
        self.assertEqual(failed, [], failed)
        self.assertEqual(m['generator'], 'export_fab.py')
        self.assertTrue(all(o['path'] and len(o['sha256']) == 64 for o in m['outputs']))
        self.assertTrue(any(config.POS_NOTE_KEEPS in n for n in m['notes']))
        drill = {c['name']: c['ok'] for c in m['checks'] if c['name'].startswith('drill: ')}
        if not m['counts'].get('drill_filled'):           # no filled vias: passes unless require_filled_vias
            self.assertTrue(drill['drill: each filled via found exactly once in the PTH file'])
            self.assertTrue(drill['drill: pcbnew sees the same filled vias (one filling/capping mode group = the '
                                  'board-text set)'])

    def test_fab_files(self):
        fab = os.path.join(self.out, 'fab')
        for kind in ('PTH', 'PTH_FILLED', 'NPTH'):
            self.assertTrue(os.path.isfile(os.path.join(fab, 'demo_v1_%s.drl' % kind)), kind)
        with open(os.path.join(fab, 'demo_v1_layer_map.csv'), encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        gerbers = [r for r in rows if r['kicad_layer'] != 'drill']
        self.assertGreaterEqual(len(gerbers), 9)
        for r in gerbers:
            self.assertTrue(os.path.isfile(os.path.join(fab, r['fab_file'])), r['fab_file'])

    def test_xyrs_and_zip(self):
        with open(os.path.join(self.out, 'assembly', 'demo_v1.XYRS'), encoding='ascii') as f:
            data = [l.rstrip('\n').split('\t') for l in f if not l.startswith('#')]
        self.assertTrue(data)
        self.assertTrue(all(len(r) == 12 for r in data))
        self.assertTrue(all(r[4] in ('1', '2') and r[10] in ('0', '1') for r in data))
        z = os.path.join(self.out, 'demo_v1_macrofab_upload.zip')
        self.assertTrue(os.path.isfile(z), self.fab_log.getvalue()[-2000:])
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            self.assertEqual(zf.getinfo('demo_v1.XYRS').date_time, (2026, 1, 2, 3, 4, 4))   # the commit date (even s)
        self.assertIn('demo_v1.XYRS', names)
        self.assertIn('demo_v1_macrofab.xlsx', names)
        self.assertTrue(all(n.count('.') == 1 for n in names))

    def test_bom_check_against_the_written_csv(self):
        with redirect_stdout(io.StringIO()) as log:
            rc = bom_check.main(['HEAD', '--repo', self.repo, '--kicad-cli', CLI,
                                 '--against', os.path.join(self.bom, 'demo_v1_bom.csv')])
        self.assertEqual(rc, 0, log.getvalue())

    def test_bom_check_export_only(self):
        d = os.path.join(self.tmp, 'bomcheck')
        with redirect_stdout(io.StringIO()) as log:
            rc = bom_check.main(['HEAD', '--repo', self.repo, '--kicad-cli', CLI, '--perref', '--out', d])
        self.assertEqual(rc, 0, log.getvalue())
        self.assertEqual(sorted(os.listdir(d)), ['HEAD.grouped.csv', 'HEAD.perref.csv'])
        with open(os.path.join(d, 'HEAD.grouped.csv'), 'rb') as a, \
                open(os.path.join(self.bom, 'demo_v1_bom.csv'), 'rb') as b:
            self.assertEqual(a.read(), b.read())      # the BOM tool writes the same grouped csv

    def test_no_pcbway_files_unless_asked(self):
        with open(os.path.join(self.out, 'docs', 'demo_v1_export_manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        self.assertNotIn('pcbway', m)
        self.assertFalse([o['path'] for o in m['outputs'] if 'pcbway' in o['path']])
        self.assertFalse([c['name'] for c in m['checks'] if c['name'].startswith('PCBWay')])

    def test_step_origin_on_a_straight_outline(self):
        with open(os.path.join(self.out, 'docs', 'demo_v1_export_manifest.json'), encoding='utf-8') as f:
            m = json.load(f)
        origin = [c for c in m['checks'] if c['name'].startswith('STEP: origin = XYRS corner')]
        self.assertEqual([c['ok'] for c in origin], [True], origin)


EDGE_ITEM_RE = re.compile(r'\t\(gr_(?:line|arc|circle|rect|poly|curve)\n(?:\t\t[^\n]*\n)*?\t\)\n')
MODEL_VAR = '${KICAD10_3DMODEL_DIR}/'


def round_outline(text):
    """The board text with its top-level Edge.Cuts shapes replaced by one circle around them."""
    items = [m for m in EDGE_ITEM_RE.finditer(text) if '\t\t(layer "Edge.Cuts")\n' in m.group(0)]
    pts = [(float(x), float(y)) for m in items
           for x, y in re.findall(r'\((?:start|end|center|mid|xy) (-?[\d.]+) (-?[\d.]+)\)', m.group(0))]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, round(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / 2 + 2)
    for m in reversed(items):
        text = text[:m.start()] + text[m.end():]
    circle = ('\t(gr_circle\n\t\t(center %g %g)\n\t\t(end %g %g)\n\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type solid)\n'
              '\t\t)\n\t\t(fill no)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "5c1d8a52-0b1c-4d3e-9f40-a1b2c3d4e5f6")\n\t)\n'
              % (cx, cy, cx + r, cy))
    return text[:items[0].start()] + circle + text[items[0].start():], 2 * r


def move_models(text, lib, models_dir):
    """Point the board's project-local models (${KIPRJMOD}/...) and its first KiCad library STEP model at
    ${KIPRJMOD}/../lib/3d_models/ and put the files in lib. kicad-cli takes no VRML into a STEP, so a project-local
    model is replaced by a copy of that KiCad STEP model under its own name."""
    paths = sorted(set(re.findall(r'\(model "([^"]+)"', text)))
    kicad = next((p for p in paths if p.startswith(MODEL_VAR) and p.lower().endswith('.step') and
                  os.path.isfile(os.path.join(models_dir, p[len(MODEL_VAR):]))), None)
    if kicad is None:
        raise unittest.SkipTest('the project uses no STEP model of the KiCad 3-D model library')
    stand_in = os.path.join(models_dir, kicad[len(MODEL_VAR):])
    moved = {kicad: os.path.basename(kicad)}
    moved.update((p, os.path.splitext(os.path.basename(p))[0] + '.step') for p in paths if p.startswith('${KIPRJMOD}/'))
    os.makedirs(lib)
    for old, new in moved.items():
        shutil.copyfile(stand_in, os.path.join(lib, new))
        text = text.replace('(model "%s"' % old, '(model "${KIPRJMOD}/../lib/3d_models/%s"' % new)
    return text, sorted(moved.values())


MODELS = config.find_kicad_3dmodel_dir(None, CLI) if CLI else None


@unittest.skipIf(REASON or not MODELS, REASON or "no KiCad 3-D model library found")
class RoundBoardLibraryFolderTest(unittest.TestCase):
    """The project at hw/demo/ with the part library hw/lib/ beside it, as kicad-project-template lays a repository
    out (library_dir = "../lib", models at ${KIPRJMOD}/../lib/3d_models/), its outline one gr_circle (a round board,
    exported to STEP as a CIRCLE: its centre and one seam point), exported with --pcbway."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='kfp_it_round_')
        cls.repo = os.path.join(cls.tmp, 'repo')
        proj = os.path.join(cls.repo, 'hw', 'demo')
        shutil.copytree(PROJECT, proj)
        board = os.path.join(proj, [f for f in os.listdir(proj) if f.endswith('.kicad_pcb')][0])
        with open(board, encoding='utf-8') as f:
            text = f.read()
        text, cls.diameter = round_outline(text)
        text, cls.models = move_models(text, os.path.join(cls.repo, 'hw', 'lib', '3d_models'), MODELS)
        with open(board, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        with open(os.path.join(cls.repo, 'kicad-fab.json'), 'w', encoding='utf-8') as f:
            json.dump({'project_dir': 'hw/demo', 'library_dir': '../lib', 'library_model_paths': ['3d_models']}, f)
        git(cls.repo, '-c', 'init.defaultBranch=main', 'init', '-q')
        git(cls.repo, 'add', '-A')
        git(cls.repo, 'commit', '-qm', 'round board, library folder')
        cls.out = os.path.join(cls.tmp, 'out')
        with redirect_stdout(io.StringIO()) as cls.log:
            cls.rc = export_fab.main(['HEAD', '--repo', cls.repo, '--out', cls.out, '--name', 'round_v1', '--pcbway',
                                      '--kicad-cli', CLI, '--kicad-python', KPY,
                                      '--work', os.path.join(cls.tmp, 'work')])
        with open(os.path.join(cls.out, 'docs', 'round_v1_export_manifest.json'), encoding='utf-8') as f:
            cls.m = json.load(f)
        cls.checks = {c['name']: c for c in cls.m['checks']}

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.tmp)

    def check(self, prefix):
        found = [c for name, c in self.checks.items() if name.startswith(prefix)]
        self.assertEqual(len(found), 1, (prefix, sorted(self.checks)))
        return found[0]

    def assert_ok(self, prefix):
        c = self.check(prefix)
        self.assertTrue(c['ok'], c)

    def test_every_step_ran(self):
        self.assertIn(self.rc, (0, 1), self.log.getvalue()[-3000:])
        self.assertEqual([s for s in self.m['steps'] if s[1] != 'ok'], [])
        self.assertIn(['PCBWay BOM + centroid', 'ok'], [s[:2] for s in self.m['steps']])
        # the zips are packed after the manifest's steps are recorded: the printed summary lists them
        self.assertRegex(self.log.getvalue(), r'\n  ok   PCBWay Gerber zip +\d+ members\n')

    def test_round_outline_and_step_origin(self):
        self.assert_ok('outline: Edge.Cuts Gerber extents = pcbnew centre-line box')
        self.assertEqual([round(v, 3) for v in self.m['board_size_mm']], [self.diameter, self.diameter])
        self.assert_ok('STEP: origin = XYRS corner (board spans 0..%.3f x 0..%.3f mm)' % (self.diameter,
                                                                                          self.diameter))

    def test_models_from_the_library_folder(self):
        self.assertIn('(folder hw/lib at ', self.m['library'])
        self.assertIn('3-D models: %d files of ../lib (folder hw/lib at ' % len(self.models),
                      self.m['models']['library'])
        self.assert_ok('STEP: ../lib 3-D models added to the project copy')
        self.assert_ok('STEP: every placed part with a model entry gets a model')
        self.assertEqual([f for f in self.m['models']['missing_files'] if '../lib/' in f], [])

    def test_pcbway_files(self):
        for prefix in ('PCBWay BOM: ', 'PCBWay centroid: ', 'PCBWay centroid vs KiCad pos: ', 'PCBWay Gerber zip: '):
            self.assert_ok(prefix)
        p = self.m['pcbway']
        self.assertEqual(p['bom'], 'assembly/round_v1_pcbway_bom.xlsx')
        counts = self.m['counts']
        self.assertEqual((p['centroid']['top']['rows'], p['centroid']['bottom']['rows']),
                         (counts['fitted_top'], counts['fitted_bottom']))
        for side in ('top', 'bottom'):
            with open(os.path.join(self.out, 'assembly', 'round_v1_pcbway_%s.csv' % side), encoding='ascii') as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], export_fab.PCBWAY_CENTROID_COLUMNS)
            self.assertEqual(len(rows) - 1, counts['fitted_' + side])
        with zipfile.ZipFile(os.path.join(self.out, 'round_v1_pcbway_gerbers.zip')) as z:
            names = z.namelist()
        drills = ['round_v1_PTH.drl'] + (['round_v1_PTH_FILLED.drl'] if counts['drill_filled'] else []) + \
            ['round_v1_NPTH.drl']
        self.assertEqual(names, [s['fab_file'] for s in self.m['layer_map']] + drills)
        self.assertEqual(p['gerber_zip']['members'], names)


if __name__ == '__main__':
    unittest.main()
