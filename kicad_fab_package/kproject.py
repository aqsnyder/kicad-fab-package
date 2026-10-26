"""Build a full KiCad project copy outside the repo (library module for the other tools, and a command of its own).

usage: kicad-project-copy DEST (--rev REV | --worktree) [--repo DIR] [--project-dir DIR] [--library auto|yes|no]
                          [--library-dir DIR] [--library-paths P1,P2] [--require-dru] [--full] [--config FILE]

DEST            empty or new directory; the project lands in DEST/<project-dir>/
--rev REV       take the files from a commit with `git archive` (read-only: nothing in the repo is touched)
--worktree      copy the files from the working tree instead (e.g. during a merge, before the commit). Library
                gitlink from the index.
--repo          the git repository (default: current directory)
--project-dir   the project folder inside the repo, "." for the top level (default: auto-detected, the folder of the
                only .kicad_pro that has a .kicad_pcb of the same name beside it, at REV)
--library       auto (default): add the library (--library-dir) when it is there: a submodule at the gitlink commit
                when the submodule checkout has that commit, a plain folder of the repository from the same commit
                (with --worktree, from the working tree); else carry on without it. yes: required; no: skip.
                Exports and DRC do not need it; ERC and footprint-library checks do.
--library-dir   the library folder, relative to the project folder (default: none): a git submodule, or a plain folder
                of the repository such as ../lib (hw/lib beside hw/<board>/, which the project reaches as
                ${KIPRJMOD}/../lib). It lands at the same place relative to the project in the copy.
--library-paths the folders of the library to copy (default: the whole library)
--require-dru   fail unless the copy has <project>.kicad_dru (default: the design-rules file is optional)
--full          copy every tracked file of the project directory (default: only what KiCad reads for DRC, ERC,
                refill and exports: every .kicad_sch, .kicad_pro, .kicad_dru, .kicad_pcb, the lib tables, Templates/)

The copy is checked: the .kicad_pro, the .kicad_pcb and the .kicad_sch (same basename) must exist, and every sheet
reachable from the root sheet (Sheetfile properties, recursively) must be present.
"""
import argparse
import datetime
import io
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile

try:
    from . import config
except ImportError:  # imported as a plain module from its folder
    import config  # noqa: F401

PROJECT_FILE_RE = re.compile(r'\.(kicad_sch|kicad_pro|kicad_dru|kicad_pcb)$|(^|/)(fp-lib-table|sym-lib-table)$')


class ProjectError(Exception):
    pass


def git(repo, *args, binary=False, check=True):
    r = subprocess.run(['git', '-C', repo] + list(args), capture_output=True)
    if check and r.returncode != 0:
        raise ProjectError('git %s: %s' % (' '.join(args), r.stderr.decode('utf-8', 'replace').strip()))
    return r.stdout if binary else r.stdout.decode('utf-8', 'replace').strip()


def iso_datetime(text):
    """A datetime from git's strict ISO 8601 date (%cI, %aI). git writes 'Z' for UTC, which Python before 3.11
    does not accept in fromisoformat()."""
    text = text.strip()
    if text[-1:] in ('Z', 'z'):
        text = text[:-1] + '+00:00'
    return datetime.datetime.fromisoformat(text)


def rev_sha(repo, rev):
    return git(repo, 'rev-parse', '--verify', rev + '^{commit}')


def norm_project_dir(project_dir):
    """Repo-relative project folder with forward slashes and no trailing slash; '' for the top level."""
    p = (project_dir or '').replace('\\', '/').strip('/')
    return '' if p in ('', '.') else p


def under(project_dir, rel):
    """rel inside the project folder, repo-relative (project_dir '' = the top level)."""
    return '%s/%s' % (project_dir, rel) if project_dir else rel


def library_path(project_dir, library_dir):
    """The library folder, repo-relative with '/' separators: library_dir taken from the project folder, so '../lib'
    from 'hw/board' is 'hw/lib'. Raises ProjectError when that is the top level or outside the repository."""
    p = posixpath.normpath(under(project_dir, library_dir.replace('\\', '/')))
    if p in ('.', '..') or p.startswith(('../', '/')):
        raise ProjectError('library folder %r from the project folder %r is %s, not a folder inside the repository'
                           % (library_dir, project_dir or '.', 'the top level' if p == '.' else 'outside it'))
    return p


def library_kind(repo, rev, path):
    """How the repo-relative library folder path is stored at commit rev (None: in the index): 'submodule' (a
    gitlink), 'folder' (files of this repository) or None (nothing there)."""
    if gitlink(repo, rev, path):
        return 'submodule'
    if rev is None:
        names = git(repo, 'ls-files', '--', path)
    else:
        names = git(repo, 'ls-tree', '-r', '--name-only', rev, '--', path)
    return 'folder' if names.strip() else None


def _pathspec(project_dir):
    return [project_dir] if project_dir else []


def _long(p):
    p = os.path.abspath(p)
    if os.name == 'nt' and len(p) > 240 and not p.startswith('\\\\?\\'):
        return '\\\\?\\' + p.replace('/', '\\')
    return p


def extract_tar(data, dest, strip_prefix=''):
    """Extract a git-archive tar (bytes) under dest; long Windows paths handled; no symlinks or absolute paths."""
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf:
            name = m.name
            if strip_prefix:
                if not name.startswith(strip_prefix):
                    continue
                name = name[len(strip_prefix):]
            parts = [x for x in name.split('/') if x]
            if not parts or any(x in ('..',) for x in parts) or name.startswith('/'):
                continue
            target = os.path.join(dest, *parts)
            if m.isdir():
                os.makedirs(_long(target), exist_ok=True)
            elif m.isfile():
                os.makedirs(_long(os.path.dirname(target)), exist_ok=True)
                with tf.extractfile(m) as src, open(_long(target), 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                n += 1
    return n


def project_paths(names, project_dir, full):
    pre = project_dir.rstrip('/') + '/' if project_dir else ''
    out = []
    for p in names:
        if not p.startswith(pre):
            continue
        rel = p[len(pre):]
        if full or ('/' not in rel and PROJECT_FILE_RE.search(rel)) or rel.startswith('Templates/'):
            if rel.endswith('.kicad_prl'):
                continue
            out.append(p)
    return out


def detect_project_dir(repo, rev=None):
    """The repo-relative folder ('' = the top level) of the only .kicad_pro that has a .kicad_pcb of the same name
    beside it, at commit rev (None: in the index). Raises ProjectError when there is not exactly one."""
    if rev is None:
        names = git(repo, 'ls-files', '-z').split('\0')
    else:
        names = git(repo, 'ls-tree', '-r', '-z', '--name-only', rev).split('\0')
    have = set(names)
    pros = sorted(n for n in names if n.endswith('.kicad_pro') and n[:-len('.kicad_pro')] + '.kicad_pcb' in have)
    if len(pros) != 1:
        raise ProjectError('cannot auto-detect the project folder: %d .kicad_pro files with a .kicad_pcb beside them '
                           '(%s); pass --project-dir' % (len(pros), ', '.join(pros[:8]) or 'none'))
    return norm_project_dir(os.path.dirname(pros[0]).replace('\\', '/'))


def same_dir(a, b):
    """True when a and b name the same folder. Compares the folders themselves, so case, slash style and Windows
    short (8.3) names such as C:/Users/RUNNER~1 cannot make one folder look like two."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def gitlink(repo, rev, path):
    """Commit sha a submodule path points at, in a commit (rev) or in the index (rev None)."""
    if rev is None:
        line = git(repo, 'ls-files', '-s', '--', path)
        m = re.match(r'160000 ([0-9a-f]{40}) ', line)
    else:
        line = git(repo, 'ls-tree', rev, '--', path)
        m = re.match(r'160000 commit ([0-9a-f]{40})\t', line)
    return m.group(1) if m else None


def add_library(repo, project_dir, sha, dest, mode, library_dir=None, paths=None):
    """Extract the library submodule <project_dir>/<library_dir> at commit sha into the copy; returns a status. sha
    None: there is no gitlink (and no folder: add_library_folder handles one)."""
    if mode == 'no':
        return 'library: skipped'
    if not library_dir:
        if mode == 'yes':
            raise ProjectError('library: required (--library yes) but no library folder is configured '
                               '(--library-dir)')
        return 'library: none configured'
    paths = list(paths or [])
    rel = library_path(project_dir, library_dir)
    if not sha:
        msg = f'library: no submodule or folder at {rel}'
        if mode == 'yes':
            raise ProjectError(msg)
        return msg + ' -> continuing without it (DRC does not need it)'
    lib = os.path.join(repo, *rel.split('/'))
    # an uninitialised submodule is an empty directory, and `git -C` would then walk up to the superproject
    top = subprocess.run(['git', '-C', lib, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    own_repo = top.returncode == 0 and bool(top.stdout.strip()) and same_dir(top.stdout.strip(), lib)
    have = own_repo and subprocess.run(['git', '-C', lib, 'cat-file', '-e', sha + '^{commit}'],
                                       capture_output=True).returncode == 0
    if not have:
        msg = f'library: commit {sha} not available in {lib}'
        if mode == 'yes':
            raise ProjectError(msg)
        return msg + ' -> continuing without it (DRC does not need it)'
    data = git(lib, 'archive', '--format=tar', sha, *(['--'] + paths if paths else []), binary=True)
    n = extract_tar(data, os.path.join(dest, *rel.split('/')))
    return f'library: {n} files of {library_dir} {sha[:9]} ({", ".join(paths) if paths else "whole tree"})'


def add_library_folder(repo, rev, project_dir, dest, mode, library_dir, paths=None):
    """Copy a library that is a plain folder of the repository (no submodule), such as library_dir '../lib' beside the
    project folder, into the copy at the same place relative to the project: from commit rev with git archive, or
    from the working tree (rev None: the files in the index). Returns a status."""
    if mode == 'no':
        return 'library: skipped'
    lib = library_path(project_dir, library_dir)
    paths = list(paths or [])
    specs = ['%s/%s' % (lib, p.replace('\\', '/').strip('/')) for p in paths] or [lib]
    if rev is None:
        names = git(repo, 'ls-files', '--', *specs).splitlines()
    else:
        names = git(repo, 'ls-tree', '-r', '--name-only', rev, '--', *specs).splitlines()
    names = [n for n in names if n]
    if not names:
        msg = f'library: folder {lib} has no files{" in " + ", ".join(paths) if paths else ""}'
        if mode == 'yes':
            raise ProjectError(msg)
        return msg + ' -> continuing without it (DRC does not need it)'
    if rev is None:
        n = 0
        for p in names:
            src, dst = os.path.join(repo, *p.split('/')), os.path.join(dest, *p.split('/'))
            if os.path.isfile(src):          # a file deleted from the working tree but still in the index
                os.makedirs(_long(os.path.dirname(dst)), exist_ok=True)
                shutil.copyfile(_long(src), _long(dst))
                n += 1
        where = 'the working tree'
    else:
        used = [s for s in specs if any(n == s or n.startswith(s + '/') for n in names)]   # an unmatched one fails
        n = extract_tar(git(repo, 'archive', '--format=tar', rev, '--', *used, binary=True), dest)
        where = rev[:9]
    return f'library: {n} files of {library_dir} (folder {lib} at {where}) ' \
           f'({", ".join(paths) if paths else "whole tree"})'


def sheet_closure(proj_dir, root_sch):
    """Every .kicad_sch reachable from root_sch; returns (found, missing)."""
    seen, missing, todo = set(), set(), [root_sch]
    while todo:
        f = todo.pop()
        if f in seen or f in missing:
            continue
        p = os.path.join(proj_dir, f)
        if not os.path.exists(p):
            missing.add(f)
            continue
        seen.add(f)
        with open(p, encoding='utf-8') as fh:
            t = fh.read()
        for m in re.finditer(r'\(property "Sheetfile" "([^"]+)"', t):
            todo.append(m.group(1).replace('\\', '/'))
    return sorted(seen), sorted(missing)


def check_project(dest, project_dir, name=None, require_dru=False):
    proj = os.path.join(dest, project_dir)
    if name is None:
        pros = [f for f in os.listdir(proj) if f.endswith('.kicad_pro')]
        if len(pros) != 1:
            raise ProjectError(f'expected one .kicad_pro in {proj}, found {pros}')
        name = pros[0][:-len('.kicad_pro')]
    exts = ('.kicad_pro', '.kicad_pcb', '.kicad_sch') + (('.kicad_dru',) if require_dru else ())
    for ext in exts:
        if not os.path.exists(os.path.join(proj, name + ext)):
            raise ProjectError(f'project copy lacks {name}{ext}')
    found, missing = sheet_closure(proj, name + '.kicad_sch')
    if missing:
        raise ProjectError(f'project copy lacks sheets {missing}')
    return name, found


def build(dest, repo='.', rev=None, worktree=False, project_dir=None, library='auto', full=False, library_dir=None,
          library_paths=None, require_dru=False):
    """Create the project copy; returns a dict describing it. project_dir None: auto-detected."""
    repo = os.path.abspath(repo)
    if os.path.exists(dest) and os.listdir(dest):
        raise ProjectError(f'{config.show_path(dest)} is not empty')
    sha = None if worktree else rev_sha(repo, rev)  # fail on a bad REV before creating anything
    project_dir = norm_project_dir(detect_project_dir(repo, sha) if project_dir is None else project_dir)
    os.makedirs(dest, exist_ok=True)
    info = {'dest': dest, 'project_dir': project_dir}
    lib_path = library_path(project_dir, library_dir) if library_dir else None
    if worktree:
        names = git(repo, 'ls-files', '--', *_pathspec(project_dir)).splitlines()
        paths = project_paths(names, project_dir, full)
        for p in paths:
            src = os.path.join(repo, p)
            if not os.path.exists(src):
                continue
            dst = os.path.join(dest, p)
            os.makedirs(_long(os.path.dirname(dst)), exist_ok=True)
            shutil.copyfile(_long(src), _long(dst))
        info['source'] = 'working tree of ' + repo
        lib_sha = gitlink(repo, None, lib_path) if lib_path else None
    else:
        names = git(repo, 'ls-tree', '-r', '--name-only', sha, '--', *_pathspec(project_dir)).splitlines()
        paths = project_paths(names, project_dir, full)
        data = git(repo, 'archive', '--format=tar', sha, '--', *paths, binary=True)
        extract_tar(data, dest)
        info['source'] = f'git archive {sha}'
        info['sha'] = sha
        lib_sha = gitlink(repo, sha, lib_path) if lib_path else None
    info['files'] = len(paths)
    if lib_path and not lib_sha and library_kind(repo, sha, lib_path) == 'folder':
        info['library'] = add_library_folder(repo, sha, project_dir, dest, library, library_dir, library_paths)
    else:
        info['library'] = add_library(repo, project_dir, lib_sha, dest, library, library_dir, library_paths)
    name, sheets = check_project(dest, project_dir, require_dru=require_dru)
    info['name'] = name
    info['sheets'] = sheets
    info['board'] = os.path.join(dest, project_dir, name + '.kicad_pcb')
    return info


def kicad_cli(path=None, check_version=True):
    """path, else KICAD_CLI, else kicad-cli in the newest standard KiCad install, else on PATH. With check_version,
    a kicad-cli older than KiCad 10 gets a warning on stderr (config.warn_if_old_kicad)."""
    p = config.find_kicad_cli(path)
    if not p:
        raise ProjectError('kicad-cli not found in the standard install folders or on PATH (use --kicad-cli or '
                           'KICAD_CLI)')
    if not os.path.exists(p):
        raise ProjectError(f'kicad-cli not found: {p} (use --kicad-cli or KICAD_CLI)')
    if check_version:
        config.warn_if_old_kicad(p)
    return p


def run_drc(cli, board, out_json, refill=False, save=False, parity=True):
    """kicad-cli pcb drc with --all-track-errors --severity-all (+ --schematic-parity, --refill-zones, --save-board)."""
    cmd = [cli, 'pcb', 'drc', '--format', 'json', '-o', out_json, '--all-track-errors', '--severity-all']
    if parity:
        cmd.append('--schematic-parity')
    if refill:
        cmd.append('--refill-zones')
    if save:
        if not refill:
            raise ProjectError('--save-board needs --refill-zones')
        cmd.append('--save-board')
    cmd.append(board)
    if os.path.exists(out_json):
        os.remove(out_json)
    r = subprocess.run(cmd, cwd=os.path.dirname(board), capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    if not os.path.exists(out_json):
        raise ProjectError('kicad-cli wrote no report:\n%s\n%s\n%s' % (' '.join(cmd), r.stdout, r.stderr))
    return cmd, r


def count_board_properties(text):
    """Top-level (property ...) items: the title-block variables a project-less Python save drops."""
    return len(re.findall(r'^\t\(property "', text, re.M))


CONFIG_KEYS = ('project_dir', 'library_dir', 'library_paths', 'require_dru')


def build_parser():
    ap = argparse.ArgumentParser(prog='kicad-project-copy', description=config.cli_description(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dest', metavar='DEST', help='empty or new folder; the project lands in DEST/<project-dir>/')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--rev', metavar='REV', help='take the files from this commit with git archive')
    g.add_argument('--worktree', action='store_true', help='copy the files from the working tree instead')
    ap.add_argument('--repo', default='.', metavar='DIR', help='the git repository (default: the current folder)')
    ap.add_argument('--library', choices=('auto', 'yes', 'no'), default='auto',
                    help='add the library (--library-dir): auto (a submodule if its checkout has the commit, a folder '
                         'if the commit has it), yes (required) or no (default: auto)')
    ap.add_argument('--full', action='store_true', help='copy every tracked file of the project folder, not only '
                                                        'what KiCad reads')
    config.add_args(ap, CONFIG_KEYS)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    a = build_parser().parse_args(argv)
    try:
        s = config.resolve(a, a.repo)
        info = build(a.dest, a.repo, a.rev, a.worktree, s.project_dir, a.library, a.full, s.library_dir,
                     s.library_paths, s.require_dru)
    except (ProjectError, config.ConfigError) as e:
        print('ERROR:', e)
        return 2
    nsch = len([f for f in os.listdir(os.path.join(a.dest, info['project_dir'])) if f.endswith('.kicad_sch')])
    print(f"{info['source']}: {info['files']} files, {nsch} .kicad_sch ({len(info['sheets'])} in the hierarchy of "
          f"{info['name']}.kicad_sch, all present)")
    print(info['library'])
    print('board:', config.show_path(info['board']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
