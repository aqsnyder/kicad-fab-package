"""End-to-end run on a real KiCad project. Skipped unless KiCad 10 (kicad-cli and its python), git and a project are
available. The project is KiCad's own pic_programmer demo, or the folder named by KFP_TEST_KICAD_PROJECT (one
.kicad_pro in it); it is committed into a scratch git repository first. Set KFP_SKIP_INTEGRATION=1 to skip."""
import csv
import io
import json
import os
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


if __name__ == '__main__':
    unittest.main()
