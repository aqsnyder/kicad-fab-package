import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

from kicad_fab_package import config, kproject

from ._util import rmtree

try:
    import tomllib  # noqa: F401
    HAVE_TOML = True
except ImportError:
    try:
        import tomli  # noqa: F401
        HAVE_TOML = True
    except ImportError:
        HAVE_TOML = False

CLEAN_ENV = {k: '' for k in ('KICAD_CLI', 'KICAD_PYTHON', 'KICAD10_PYTHON', 'KICAD10_3DMODEL_DIR',
                             config.CONFIG_ENV)}


def parser(keys=tuple(config.FLAGS)):
    ap = argparse.ArgumentParser()
    config.add_args(ap, keys)
    return ap


class TmpDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kfp_cfg_')
        p = mock.patch.dict(os.environ, CLEAN_ENV)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        rmtree(self.tmp)

    def write_json(self, data, name='kicad-fab.json'):
        p = os.path.join(self.tmp, name)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        return p


class LoadConfigTest(TmpDirTest):
    def test_defaults_without_a_file(self):
        s = config.resolve(None, self.tmp)
        self.assertIsNone(s.config_path)
        self.assertEqual(s.name_template, '{project}_v{revision}')
        self.assertIsNone(s.library_dir)
        self.assertEqual(s.library_paths, [])
        self.assertEqual(s.generator_prefix, '')
        self.assertFalse(s.require_dru)
        self.assertEqual(s.baseline_label, 'baseline')
        self.assertEqual(s.revision_label, 'v{revision}')
        self.assertEqual(s.non_part_refs, r'^(FID|H)\d+$')
        self.assertEqual(s.non_part_libs, ['Fiducial', 'MountingHole'])
        self.assertEqual(s.xyrs_non_part_refs, s.non_part_refs)       # inherited
        self.assertEqual(s.xyrs_non_part_libs, s.non_part_libs)
        self.assertFalse(s.require_filled_vias)
        self.assertIn('fiducials and mounting holes', s.pos_note_keeps)

    def test_non_part_and_note_settings(self):
        p = self.write_json({'non_part_refs': '', 'xyrs_non_part_refs': r'^(FID|H)\d+$', 'xyrs_non_part_libs': [],
                             'require_filled_vias': True, 'pos_note_keeps': 'the test points',
                             'revision_label': 'rev {revision}'})
        s = config.resolve(None, self.tmp, config_path=p)
        self.assertEqual((s.non_part_refs, s.non_part_libs), ('', ['Fiducial', 'MountingHole']))
        self.assertEqual((s.xyrs_non_part_refs, s.xyrs_non_part_libs), (r'^(FID|H)\d+$', []))
        self.assertIsNone(config.compile_refs(s.non_part_refs))
        self.assertTrue(config.compile_refs(s.xyrs_non_part_refs).match('H3'))
        self.assertTrue(s.require_filled_vias)
        self.assertEqual(s.pos_note_keeps, 'the test points')
        self.assertEqual(config.format_name(s.revision_label, 'b', '2'), 'rev 2')
        # the XYRS keys follow the shared ones unless set
        args = parser().parse_args(['--non-part-refs', 'MH\\d+', '--non-part-libs', 'Mech'])
        s = config.resolve(args, self.tmp, config_path=self.write_json({}, 'empty.json'))
        self.assertEqual((s.xyrs_non_part_refs, s.xyrs_non_part_libs), ('MH\\d+', ['Mech']))

    def test_bad_regex_and_label(self):
        for bad in ({'non_part_refs': '(FID'}, {'xyrs_non_part_refs': '['}, {'revision_label': 'v{rev}'},
                    {'non_part_libs': 'Fiducial'}, {'require_filled_vias': 1}):
            p = self.write_json(bad, 'bad.json')
            with self.assertRaises(config.ConfigError, msg=str(bad)):
                config.load_config(p)
        with self.assertRaises(config.ConfigError):
            config.resolve(parser().parse_args(['--non-part-refs', '(']), self.tmp)

    def test_bool_flags_turn_a_config_value_off(self):
        p = self.write_json({'require_dru': True, 'require_filled_vias': True})
        s = config.resolve(parser().parse_args(['--config', p]), self.tmp)
        self.assertEqual((s.require_dru, s.require_filled_vias), (True, True))
        s = config.resolve(parser().parse_args(['--config', p, '--no-require-dru', '--no-require-filled-vias']),
                           self.tmp)
        self.assertEqual((s.require_dru, s.require_filled_vias), (False, False))
        s = config.resolve(parser().parse_args(['--require-filled-vias']), self.tmp)
        self.assertTrue(s.require_filled_vias)

    def test_help_lists_both_flags_of_every_bool_key(self):
        listed = {line.split()[0] for line in parser().format_help().splitlines() if line.startswith('  -')}
        for key, (_, kind) in config.KEYS.items():
            if kind == 'bool' and key in config.FLAGS:
                flag = config.FLAGS[key][0]
                self.assertIn(flag, listed)
                self.assertIn('--no-' + flag[2:], listed)

    def test_json_file_is_found_at_the_repo_top_and_validated(self):
        self.write_json({'project_dir': 'hw', 'library_dir': 'libs/parts/', 'library_paths': ['fp', 'sym'],
                         'kicad_python': 'bin/python', 'require_dru': True, 'baseline_label': 'v1.1'})
        s = config.resolve(None, self.tmp)
        self.assertEqual(os.path.normcase(s.config_path), os.path.normcase(os.path.join(self.tmp, 'kicad-fab.json')))
        self.assertEqual(s.project_dir, 'hw')
        self.assertEqual(s.library_dir, 'libs/parts')              # trailing slash dropped
        self.assertEqual(s.library_paths, ['fp', 'sym'])
        self.assertTrue(s.require_dru)
        self.assertEqual(os.path.normcase(s.kicad_python),
                         os.path.normcase(os.path.join(self.tmp, 'bin', 'python')))   # relative to the file

    def test_unknown_key_and_bad_types(self):
        for bad in ({'projct_dir': 'x'}, {'library_paths': 'fp'}, {'require_dru': 'yes'}, {'project_dir': 3},
                    {'name_template': '{board}_{rev}'}):
            p = self.write_json(bad, 'bad.json')
            with self.assertRaises(config.ConfigError):
                config.load_config(p)
        with self.assertRaises(config.ConfigError):
            config.find_config(os.path.join(self.tmp, 'missing.json'))

    def test_null_means_default(self):
        p = self.write_json({'library_dir': None, 'name_template': None}, 'n.json')
        self.assertEqual(config.load_config(p), {})

    @unittest.skipUnless(HAVE_TOML, 'needs Python 3.11+ or tomli')
    def test_toml_file(self):
        with open(os.path.join(self.tmp, 'kicad-fab.toml'), 'w', encoding='utf-8') as f:
            f.write('project_dir = "board"\nname_template = "rev_{revision}"\nlibrary_model_paths = ["3d"]\n')
        s = config.resolve(None, self.tmp)
        self.assertEqual((s.project_dir, s.name_template, s.library_model_paths), ('board', 'rev_{revision}', ['3d']))

    def test_env_var_names_the_file(self):
        p = self.write_json({'generator_prefix': 'tools/'}, 'elsewhere.json')
        with mock.patch.dict(os.environ, {config.CONFIG_ENV: p}):
            self.assertEqual(config.resolve(None, '.').generator_prefix, 'tools/')


class PrecedenceTest(TmpDirTest):
    def test_flag_beats_env_beats_config(self):
        p = self.write_json({'kicad_cli': '/from/config', 'project_dir': 'cfg', 'library_paths': ['a']})
        args = parser().parse_args(['--config', p])
        self.assertEqual(os.path.basename(config.resolve(args, self.tmp).kicad_cli), 'config')
        with mock.patch.dict(os.environ, {'KICAD_CLI': '/from/env'}):
            self.assertEqual(config.resolve(args, self.tmp).kicad_cli, '/from/env')
            args = parser().parse_args(['--config', p, '--kicad-cli', '/from/flag', '--project-dir', 'flag',
                                        '--library-paths', 'x, y', '--require-dru'])
            s = config.resolve(args, self.tmp)
            self.assertEqual((s.kicad_cli, s.project_dir, s.library_paths, s.require_dru),
                             ('/from/flag', 'flag', ['x', 'y'], True))

    def test_library_dir_flag_can_clear_the_config(self):
        p = self.write_json({'library_dir': 'lib'})
        args = parser().parse_args(['--config', p, '--library-dir', ''])
        self.assertIsNone(config.resolve(args, self.tmp).library_dir)

    def test_kicad10_python_env_is_honoured(self):
        with mock.patch.dict(os.environ, {'KICAD10_PYTHON': '/k10/python'}):
            self.assertEqual(config.resolve(None, self.tmp).kicad_python, '/k10/python')
            self.assertEqual(config.find_kicad_python(None), '/k10/python')

    def test_overrides_win(self):
        p = self.write_json({'project_dir': 'cfg'})
        self.assertEqual(config.resolve(None, self.tmp, config_path=p, project_dir='lib').project_dir, 'lib')


class NameTest(unittest.TestCase):
    def test_format_name(self):
        self.assertEqual(config.format_name('{project}_v{revision}', 'myboard', '1.2'), 'myboard_v1.2')
        self.assertIsNone(config.format_name('{project}_v{revision}', 'myboard', ''))
        self.assertEqual(config.format_name('{project}', 'myboard', None), 'myboard')
        self.assertEqual(config.format_name('acme_v{revision}', 'x', '3'), 'acme_v3')

    def test_csv_list(self):
        self.assertEqual(config.csv_list(' a, b ,,c'), ['a', 'b', 'c'])
        self.assertEqual(config.csv_list(''), [])


class DetectionTest(TmpDirTest):
    def touch(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').close()
        return p

    def test_explicit_paths_win(self):
        self.assertEqual(config.find_kicad_cli('/x/kicad-cli'), '/x/kicad-cli')
        self.assertEqual(config.find_kicad_python('/x/python'), '/x/python')
        self.assertEqual(config.find_kicad_3dmodel_dir('/x/3d'), '/x/3d')
        with mock.patch.dict(os.environ, {'KICAD10_3DMODEL_DIR': '/env/3d'}):
            self.assertEqual(config.find_kicad_3dmodel_dir(None), '/env/3d')

    @unittest.skipUnless(os.name == 'nt', 'Windows install layout')
    def test_windows_newest_install_first(self):
        for v in ('9.0', '10.0', '8.0'):
            self.touch('KiCad', v, 'bin', 'kicad-cli.exe')
            self.touch('KiCad', v, 'bin', 'python.exe')
            os.makedirs(os.path.join(self.tmp, 'KiCad', v, 'share', 'kicad', '3dmodels'))
        env = {'ProgramW6432': self.tmp, 'ProgramFiles': self.tmp, 'ProgramFiles(x86)': '', 'LOCALAPPDATA': '',
               'PATH': ''}
        with mock.patch.dict(os.environ, env):
            root = self.tmp.replace('\\', '/')
            self.assertEqual(config.windows_kicad_bins()[0], root + '/KiCad/10.0/bin')
            cli = config.find_kicad_cli()
            self.assertEqual(cli, root + '/KiCad/10.0/bin/kicad-cli.exe')
            self.assertEqual(config.find_kicad_python(None, cli), root + '/KiCad/10.0/bin/python.exe')
            self.assertEqual(config.find_kicad_3dmodel_dir(None, cli), root + '/KiCad/10.0/share/kicad/3dmodels')

    @unittest.skipIf(os.name == 'nt' or sys.platform == 'darwin', 'Linux install layout')
    def test_linux_layout_next_to_cli(self):
        cli = self.touch('usr', 'bin', 'kicad-cli')
        self.touch('usr', 'bin', 'python3')
        os.makedirs(os.path.join(self.tmp, 'usr', 'share', 'kicad', '3dmodels'))
        self.assertEqual(config.find_kicad_python(None, cli), os.path.join(os.path.dirname(cli), 'python3'))
        self.assertEqual(config.find_kicad_3dmodel_dir(None, cli),
                         os.path.normpath(os.path.join(self.tmp, 'usr', 'share', 'kicad', '3dmodels')))

    def test_standard_install_wins_over_path(self):
        installed = self.touch('KiCad', '10.0', 'bin', 'kicad-cli.exe')
        on_path = self.touch('old', 'bin', 'kicad-cli.exe')
        with mock.patch.object(config, 'kicad_cli_candidates', return_value=[installed]), \
                mock.patch.object(config.shutil, 'which', return_value=on_path):
            self.assertEqual(config.find_kicad_cli(), installed)
        with mock.patch.object(config, 'kicad_cli_candidates', return_value=[os.path.join(self.tmp, 'none')]), \
                mock.patch.object(config.shutil, 'which', return_value=on_path):
            self.assertEqual(config.find_kicad_cli(), on_path)          # PATH only when no standard install
        with mock.patch.dict(os.environ, {'KICAD_CLI': os.path.join(self.tmp, 'missing')}):
            self.assertEqual(config.find_kicad_cli(), os.path.join(self.tmp, 'missing'))   # never auto-detected

    def test_old_kicad_cli_warns_once(self):
        cli = self.touch('k9', 'bin', 'kicad-cli.exe')
        err = io.StringIO()
        with mock.patch.object(config, 'kicad_cli_version', return_value=('9.0.8', 9)):
            self.assertEqual(config.warn_if_old_kicad(cli, err), 9)
            config.warn_if_old_kicad(cli, err)
        self.assertEqual(err.getvalue().count('WARNING'), 1)
        self.assertIn('is KiCad 9.0.8', err.getvalue())
        with mock.patch.object(config, 'kicad_cli_version', return_value=('10.0.7', 10)):
            self.assertEqual(config.warn_if_old_kicad(cli + '.new', err), 10)
        self.assertEqual(err.getvalue().count('WARNING'), 1)

    def test_kproject_kicad_cli_checks_the_version(self):
        cli = self.touch('k8', 'bin', 'kicad-cli.exe')
        err = io.StringIO()
        with mock.patch.object(config, 'kicad_cli_version', return_value=('8.0.9', 8)), redirect_stderr(err):
            self.assertEqual(kproject.kicad_cli(cli), cli)
        self.assertIn('WARNING', err.getvalue())

    def test_version_of_a_missing_cli_is_unknown(self):
        self.assertEqual(config.kicad_cli_version(os.path.join(self.tmp, 'no-such-cli')), (None, None))

    def test_candidates_are_strings(self):
        for c in config.kicad_cli_candidates() + config.kicad_python_candidates() + config.kicad_3dmodel_candidates():
            self.assertIsInstance(c, str)


if __name__ == '__main__':
    unittest.main()
