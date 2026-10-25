"""Project copies and library staging on synthetic git repositories (needs git; no KiCad)."""
import datetime
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout

from kicad_fab_package import kproject, models3d

from ._util import rmtree

HAVE_GIT = shutil.which('git') is not None


def git(cwd, *args):
    r = subprocess.run(['git', '-C', cwd, '-c', 'user.name=test', '-c', 'user.email=test', '-c',
                        'commit.gpgsign=false', '-c', 'core.autocrlf=false', '-c', 'core.longpaths=true'] + list(args),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('git %s: %s' % (' '.join(args), r.stderr))
    return r.stdout.strip()


def put(root, rel, text='x'):
    p = os.path.join(root, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return rel


def new_repo(path):
    os.makedirs(path)
    git(path, '-c', 'init.defaultBranch=main', 'init', '-q')
    return path


def short_path(path):
    """Windows short (8.3) form of an existing path, or None where Windows gives none."""
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value if 0 < n < len(buf) else None


PROJECT = {
    'myboard.kicad_pro': '{}',
    'myboard.kicad_pcb': '(kicad_pcb (version 20250000))\n',
    'myboard.kicad_sch': '(kicad_sch\n\t(sheet\n\t\t(property "Sheetfile" "sub.kicad_sch")\n\t)\n)\n',
    'sub.kicad_sch': '(kicad_sch)\n',
    'fp-lib-table': '(fp_lib_table)\n',
    'myboard.kicad_prl': '{}',
    'Templates/note.txt': 'template',
    'docs/readme.md': 'not copied by default',
}


@unittest.skipUnless(HAVE_GIT, 'git not installed')
class ProjectCopyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kfp_proj_')
        self.repo = new_repo(os.path.join(self.tmp, 'repo'))
        files = [put(self.repo, 'hw/' + rel, text) for rel, text in PROJECT.items()]
        git(self.repo, 'add', '--', *files)
        git(self.repo, 'commit', '-qm', 'project')

    def tearDown(self):
        rmtree(self.tmp)

    def dest(self, name='copy'):
        return os.path.join(self.tmp, name)

    def test_build_auto_detects_and_copies_what_kicad_reads(self):
        info = kproject.build(self.dest(), self.repo, rev='HEAD')
        self.assertEqual(info['project_dir'], 'hw')
        self.assertEqual(info['name'], 'myboard')
        self.assertEqual(info['sheets'], ['myboard.kicad_sch', 'sub.kicad_sch'])
        self.assertEqual(info['library'], 'library: none configured')
        proj = os.path.join(self.dest(), 'hw')
        self.assertEqual(sorted(os.listdir(proj)), ['Templates', 'fp-lib-table', 'myboard.kicad_pcb',
                                                    'myboard.kicad_pro', 'myboard.kicad_sch', 'sub.kicad_sch'])
        self.assertTrue(info['source'].startswith('git archive '))
        self.assertEqual(len(info['sha']), 40)

    def test_full_copy_and_worktree_mode(self):
        info = kproject.build(self.dest(), self.repo, rev='HEAD', project_dir='hw', full=True)
        self.assertTrue(os.path.exists(os.path.join(self.dest(), 'hw', 'docs', 'readme.md')))
        self.assertFalse(os.path.exists(os.path.join(self.dest(), 'hw', 'myboard.kicad_prl')))
        put(self.repo, 'hw/sub.kicad_sch', '(kicad_sch (changed))\n')
        info = kproject.build(self.dest('wt'), self.repo, worktree=True, project_dir='hw')
        with open(os.path.join(self.dest('wt'), 'hw', 'sub.kicad_sch'), encoding='utf-8') as f:
            self.assertIn('changed', f.read())
        self.assertTrue(info['source'].startswith('working tree of '))

    def test_checks(self):
        with self.assertRaises(kproject.ProjectError):
            kproject.build(self.dest(), self.repo, rev='HEAD', require_dru=True)    # no myboard.kicad_dru
        git(self.repo, 'rm', '-q', 'hw/sub.kicad_sch')
        git(self.repo, 'commit', '-qm', 'drop a sheet')
        with self.assertRaises(kproject.ProjectError) as e:
            kproject.build(self.dest('b'), self.repo, rev='HEAD')
        self.assertIn('lacks sheets', str(e.exception))
        os.makedirs(self.dest('c'))
        put(self.dest('c'), 'x', 'occupied')
        with self.assertRaises(kproject.ProjectError):
            kproject.build(self.dest('c'), self.repo, rev='HEAD')
        with self.assertRaises(kproject.ProjectError):
            kproject.build(self.dest('d'), self.repo, rev='no-such-rev')

    def test_detect_project_dir(self):
        self.assertEqual(kproject.detect_project_dir(self.repo, 'HEAD'), 'hw')
        self.assertEqual(kproject.detect_project_dir(self.repo), 'hw')            # the index
        files = [put(self.repo, 'old/old.kicad_pro', '{}'), put(self.repo, 'old/old.kicad_pcb', '()')]
        git(self.repo, 'add', '--', *files)
        git(self.repo, 'commit', '-qm', 'second project')
        with self.assertRaises(kproject.ProjectError):
            kproject.detect_project_dir(self.repo, 'HEAD')

    def test_top_level_project(self):
        repo = new_repo(os.path.join(self.tmp, 'top'))
        files = [put(repo, rel, text) for rel, text in PROJECT.items()]
        git(repo, 'add', '--', *files)
        git(repo, 'commit', '-qm', 'top level')
        self.assertEqual(kproject.detect_project_dir(repo, 'HEAD'), '')
        info = kproject.build(self.dest(), repo, rev='HEAD', project_dir='.')
        self.assertEqual(info['project_dir'], '')
        self.assertTrue(os.path.isfile(info['board']))

    def test_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = kproject.main([self.dest(), '--rev', 'HEAD', '--repo', self.repo])
        self.assertEqual(rc, 0)
        self.assertIn('2 in the hierarchy of myboard.kicad_sch, all present', out.getvalue())

    def test_project_paths_and_helpers(self):
        names = ['hw/a.kicad_pcb', 'hw/sub/b.kicad_sch', 'hw/Templates/t', 'hw/x.kicad_prl', 'other/c.kicad_pcb']
        self.assertEqual(kproject.project_paths(names, 'hw', False), ['hw/a.kicad_pcb', 'hw/Templates/t'])
        self.assertEqual(kproject.project_paths(names, 'hw', True), ['hw/a.kicad_pcb', 'hw/sub/b.kicad_sch',
                                                                     'hw/Templates/t'])
        self.assertEqual(kproject.norm_project_dir('./'), '')
        self.assertEqual(kproject.norm_project_dir('a\\b/'), 'a/b')
        self.assertEqual(kproject.under('', 'lib'), 'lib')
        self.assertEqual(kproject.under('hw', 'lib'), 'hw/lib')
        self.assertEqual(kproject.count_board_properties('(kicad_pcb\n\t(property "A" "1")\n\t(property "B" "2")\n'), 2)
        with self.assertRaises(kproject.ProjectError):
            kproject.kicad_cli(os.path.join(self.tmp, 'no-kicad-cli'))

    def test_iso_datetime_accepts_git_utc_z(self):
        utc = datetime.timezone.utc
        self.assertEqual(kproject.iso_datetime('2026-10-22T09:00:00Z'), datetime.datetime(2026, 10, 22, 9, tzinfo=utc))
        self.assertEqual(kproject.iso_datetime('2026-10-22T11:00:00+02:00\n'),       # git output ends in a newline
                         datetime.datetime(2026, 10, 22, 9, tzinfo=utc))

    def test_extract_tar_refuses_escapes(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tf:
            for name in ('ok/file.txt', '../evil.txt', '/abs.txt'):
                data = b'data'
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
        dest = self.dest('tar')
        self.assertEqual(kproject.extract_tar(buf.getvalue(), dest), 1)
        self.assertTrue(os.path.isfile(os.path.join(dest, 'ok', 'file.txt')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'evil.txt')))


@unittest.skipUnless(HAVE_GIT, 'git not installed')
class LibraryTest(unittest.TestCase):
    """A library submodule: its own repository inside the project folder, recorded as a gitlink."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='kfp_lib_')
        self.repo = new_repo(os.path.join(self.tmp, 'repo'))
        files = [put(self.repo, 'hw/' + rel, text) for rel, text in PROJECT.items()]
        lib = new_repo(os.path.join(self.repo, 'hw', 'parts'))
        lib_files = [put(lib, rel) for rel in ('footprints/R.kicad_mod', 'symbols/R.kicad_sym', 'models/r.step',
                                               'models/sub/c.wrl')]
        git(lib, 'add', '--', *lib_files)
        git(lib, 'commit', '-qm', 'library')
        self.lib_sha = git(lib, 'rev-parse', 'HEAD')
        git(self.repo, 'add', '--', *files)
        git(self.repo, 'update-index', '--add', '--cacheinfo', '160000,%s,hw/parts' % self.lib_sha)
        git(self.repo, 'commit', '-qm', 'project with library')

    def tearDown(self):
        rmtree(self.tmp)

    def test_gitlink(self):
        self.assertEqual(kproject.gitlink(self.repo, 'HEAD', 'hw/parts'), self.lib_sha)
        self.assertEqual(kproject.gitlink(self.repo, None, 'hw/parts'), self.lib_sha)
        self.assertIsNone(kproject.gitlink(self.repo, 'HEAD', 'hw/none'))

    def test_same_dir(self):
        lib = os.path.join(self.repo, 'hw', 'parts')
        self.assertTrue(kproject.same_dir(lib, os.path.join(self.repo, 'hw', '.', 'parts')))
        self.assertTrue(kproject.same_dir(lib.replace('\\', '/'), lib))
        self.assertFalse(kproject.same_dir(lib, self.repo))
        self.assertFalse(kproject.same_dir(lib, os.path.join(self.tmp, 'missing')))

    @unittest.skipUnless(os.name == 'nt', 'Windows short (8.3) names')
    def test_build_from_a_short_name_path(self):
        # GitHub's Windows runners hand out temp folders as C:/Users/RUNNER~1/...: git reports the library's
        # top level in long form, so a plain string compare took the initialised library for a missing one.
        short = short_path(self.repo)
        if not short or os.path.normcase(short) == os.path.normcase(self.repo):
            self.skipTest('no distinct 8.3 name on this volume')
        info = kproject.build(os.path.join(self.tmp, 'copy_short'), short, rev='HEAD', library_dir='parts',
                              library_paths=['footprints'])
        self.assertEqual(info['library'], 'library: 1 files of parts %s (footprints)' % self.lib_sha[:9])

    def test_build_adds_the_library(self):
        dest = os.path.join(self.tmp, 'copy')
        info = kproject.build(dest, self.repo, rev='HEAD', library_dir='parts',
                              library_paths=['footprints', 'symbols'])
        self.assertEqual(info['library'], 'library: 2 files of parts %s (footprints, symbols)' % self.lib_sha[:9])
        self.assertTrue(os.path.isfile(os.path.join(dest, 'hw', 'parts', 'footprints', 'R.kicad_mod')))
        self.assertFalse(os.path.exists(os.path.join(dest, 'hw', 'parts', 'models')))
        dest2 = os.path.join(self.tmp, 'copy2')
        info = kproject.build(dest2, self.repo, rev='HEAD', library_dir='parts')
        self.assertEqual(info['library'], 'library: 4 files of parts %s (whole tree)' % self.lib_sha[:9])

    def test_library_modes(self):
        self.assertEqual(kproject.add_library(self.repo, 'hw', self.lib_sha, self.tmp, 'no', 'parts'),
                         'library: skipped')
        with self.assertRaises(kproject.ProjectError):
            kproject.add_library(self.repo, 'hw', self.lib_sha, self.tmp, 'yes', None)
        msg = kproject.add_library(self.repo, 'hw', '0' * 40, self.tmp, 'auto', 'parts')
        self.assertIn('not available', msg)
        with self.assertRaises(kproject.ProjectError):
            kproject.add_library(self.repo, 'hw', '0' * 40, self.tmp, 'yes', 'parts')

    def test_library_models_tree_and_flat_copies(self):
        staging = os.path.join(self.tmp, 'staging')
        st = models3d.library_models(self.repo, 'HEAD', False, staging, 'hw', 'parts', ['models'])
        self.assertTrue(st.startswith('3-D models: 2 files of parts %s from ' % self.lib_sha[:9]))
        for rel in ('parts/models/r.step', 'parts/models/sub/c.wrl', 'r.step', 'c.wrl'):
            self.assertTrue(os.path.isfile(os.path.join(staging, *rel.split('/'))), rel)
        self.assertFalse(os.path.exists(os.path.join(staging, 'parts', 'footprints')))
        st = models3d.library_models(self.repo, None, True, os.path.join(self.tmp, 's2'), 'hw', 'parts')
        self.assertIn('4 files of parts', st)

    def test_library_models_errors(self):
        with self.assertRaises(models3d.ModelLibraryError):
            models3d.library_models(self.repo, 'HEAD', False, os.path.join(self.tmp, 's'), 'hw', 'nolib')
        # a gitlink to a commit that no checkout has
        git(self.repo, 'update-index', '--cacheinfo', '160000,%s,hw/parts' % ('1' * 40))
        git(self.repo, 'commit', '-qm', 'dangling gitlink')
        with self.assertRaises(models3d.ModelLibraryError) as e:
            models3d.library_models(self.repo, 'HEAD', False, os.path.join(self.tmp, 's'), 'hw', 'parts')
        self.assertIn('no parts checkout has commit', str(e.exception))


if __name__ == '__main__':
    unittest.main()
