"""3-D models of a library, staged for a project copy (library module).

library_models() puts the model files of the library <project_dir>/<library_dir> under <proj>/<library_dir>/... and also
flat in <proj> (some footprints name a bare model file, which KiCad resolves against the project folder). The library
is either a git submodule, taken at the commit the board's revision points the submodule at, or a plain folder of the
repository (such as ../lib beside the project folder), taken from the same commit as the board. A submodule's checkout
is the work tree's own submodule if it is initialised and has the commit, else the main checkout's (a linked git
worktree usually has an empty submodule).
"""
import io
import os
import subprocess
import tarfile

try:
    from .kproject import library_path, ProjectError, same_dir
except ImportError:  # imported as a plain module from its folder
    from kproject import library_path, ProjectError, same_dir


class ModelLibraryError(Exception):
    pass


def _run(cmd, binary=False):
    r = subprocess.run(cmd, capture_output=True, text=not binary)
    if r.returncode:
        err = r.stderr if not binary else r.stderr.decode('utf-8', 'replace')
        out = r.stdout if not binary else r.stdout.decode('utf-8', 'replace')
        raise ModelLibraryError('command failed: %s\n%s\n%s' % (' '.join(cmd), out[-2000:], err[-2000:]))
    return r.stdout


def _stage(files, proj, library_dir):
    """Write each (path inside the library, bytes) under proj/<library_dir>/ and flat in proj; returns the count."""
    n = 0
    for rel, blob in files:
        for dst in (os.path.normpath(os.path.join(proj, *library_dir.split('/'), *rel.split('/'))),
                    os.path.join(proj, os.path.basename(rel))):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as f:
                f.write(blob)
        n += 1
    return n


def _tar_files(data, strip=''):
    """(name without the strip prefix, bytes) of every file in a git-archive tar."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.startswith(strip):
                yield m.name[len(strip):], tf.extractfile(m).read()


def library_models(top, rev, worktree, proj, project_dir, library_dir, model_paths=None):
    """Stage the library's 3-D models into proj; returns a short status string.

    top: the repo work tree; rev: the commit (ignored with worktree=True, which reads the index and, for a folder,
    the working tree); project_dir: repo-relative project folder ('' = top level); library_dir: the library folder
    relative to it (a submodule, or a plain folder such as '../lib'; a '..' tree lands outside proj, so give a proj
    nested as deep as the project folder); model_paths: folders inside the library to take (empty or None: the whole
    library). Raises ModelLibraryError when there is neither a gitlink nor a folder, or no checkout has the
    submodule's commit."""
    try:
        sub = library_path(project_dir, library_dir)
    except ProjectError as e:
        raise ModelLibraryError(str(e))
    paths = [p.replace('\\', '/').strip('/') for p in (model_paths or [])]
    if worktree:
        entries = _run(['git', '-C', top, 'ls-files', '-s', '--', sub]).splitlines()
        sha = next((e.split()[1] for e in entries if e.startswith('160000 ') and e.split('\t', 1)[-1] == sub), '')
    else:
        entries = _run(['git', '-C', top, 'ls-tree', rev, '--', sub]).splitlines()
        sha = next((e.split()[2] for e in entries if e.startswith('160000 commit ')), '')
    if not sha:
        if not entries:
            raise ModelLibraryError('no %s gitlink or folder at %s' % (library_dir, 'the index' if worktree else rev))
        return _folder_models(top, None if worktree else rev, proj, sub, library_dir, paths)
    common = _run(['git', '-C', top, 'rev-parse', '--path-format=absolute', '--git-common-dir']).strip()
    cands = [os.path.join(top, *sub.split('/')), os.path.join(os.path.dirname(common), *sub.split('/'))]
    for lib in cands:
        r = subprocess.run(['git', '-C', lib, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        own = r.returncode == 0 and bool(r.stdout.strip()) and same_dir(r.stdout.strip(), lib)
        if own and subprocess.run(['git', '-C', lib, 'cat-file', '-e', sha + '^{commit}'],
                                  capture_output=True).returncode == 0:
            data = subprocess.run(['git', '-C', lib, 'archive', '--format=tar', sha] + (['--'] + paths if paths else []),
                                  capture_output=True, check=True).stdout
            n = _stage(_tar_files(data), proj, library_dir)
            return '3-D models: %d files of %s %s from %s' % (n, library_dir, sha[:9], lib)
    raise ModelLibraryError('no %s checkout has commit %s (looked in %s)' % (library_dir, sha, ', '.join(cands)))


def _folder_models(top, rev, proj, sub, library_dir, paths):
    """library_models() for a library that is a plain folder sub of the repository: its files at commit rev (None:
    the files in the index, read from the working tree)."""
    specs = ['%s/%s' % (sub, p) for p in paths] or [sub]
    if rev is None:
        names = [n for n in _run(['git', '-C', top, 'ls-files', '--'] + specs).splitlines() if n]
    else:
        names = [n for n in _run(['git', '-C', top, 'ls-tree', '-r', '--name-only', rev, '--'] + specs).splitlines()
                 if n]
    if not names:
        raise ModelLibraryError('folder %s has no files in %s' % (sub, ', '.join(specs)))
    if rev is None:
        def files():
            for name in names:
                path = os.path.join(top, *name.split('/'))
                if os.path.isfile(path):
                    with open(path, 'rb') as f:
                        yield name[len(sub) + 1:], f.read()
        n = _stage(files(), proj, library_dir)
        where = 'the working tree'
    else:
        used = [s for s in specs if any(n == s or n.startswith(s + '/') for n in names)]   # an unmatched one fails
        n = _stage(_tar_files(_run(['git', '-C', top, 'archive', '--format=tar', rev, '--'] + used, binary=True),
                              sub + '/'), proj, library_dir)
        where = rev[:9]
    return '3-D models: %d files of %s (folder %s at %s)' % (n, library_dir, sub, where)
