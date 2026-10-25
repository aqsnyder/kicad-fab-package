"""3-D models of a library submodule, staged for a project copy (library module).

library_models() puts the model files of the library submodule <project_dir>/<library_dir>, at the commit the board's
revision points the submodule at, under <proj>/<library_dir>/... and also flat in <proj> (some footprints name a bare
model file, which KiCad resolves against the project folder). The library checkout is the work tree's own submodule if
it is initialised and has the commit, else the main checkout's (a linked git worktree usually has an empty submodule).
"""
import io
import os
import subprocess
import tarfile

try:
    from .kproject import same_dir
except ImportError:  # imported as a plain module from its folder
    from kproject import same_dir


class ModelLibraryError(Exception):
    pass


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise ModelLibraryError('command failed: %s\n%s\n%s' % (' '.join(cmd), r.stdout[-2000:], r.stderr[-2000:]))
    return r.stdout


def library_models(top, rev, worktree, proj, project_dir, library_dir, model_paths=None):
    """Stage the library's 3-D models into proj; returns a short status string.

    top: the repo work tree; rev: the commit (ignored with worktree=True, which reads the gitlink from the index);
    project_dir: repo-relative project folder ('' = top level); library_dir: the submodule folder relative to it;
    model_paths: folders inside the library to take (empty or None: the whole library).
    Raises ModelLibraryError when there is no gitlink or no checkout has the commit."""
    sub = '/'.join(x for x in (project_dir, library_dir) if x)
    if worktree:
        line = _run(['git', '-C', top, 'ls-files', '-s', sub]).split()
        sha = line[1] if len(line) > 1 else ''
    else:
        line = _run(['git', '-C', top, 'ls-tree', rev, sub]).split()
        sha = line[2] if len(line) > 2 else ''
    if not sha:
        raise ModelLibraryError('no %s gitlink at %s' % (library_dir, rev))
    common = _run(['git', '-C', top, 'rev-parse', '--path-format=absolute', '--git-common-dir']).strip()
    cands = [os.path.join(top, *sub.split('/')), os.path.join(os.path.dirname(common), *sub.split('/'))]
    paths = list(model_paths or [])
    for lib in cands:
        r = subprocess.run(['git', '-C', lib, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        own = r.returncode == 0 and bool(r.stdout.strip()) and same_dir(r.stdout.strip(), lib)
        if own and subprocess.run(['git', '-C', lib, 'cat-file', '-e', sha + '^{commit}'],
                                  capture_output=True).returncode == 0:
            data = subprocess.run(['git', '-C', lib, 'archive', '--format=tar', sha] + (['--'] + paths if paths else []),
                                  capture_output=True, check=True).stdout
            n = 0
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    blob = tf.extractfile(m).read()
                    for dst in (os.path.join(proj, *library_dir.split('/'), *m.name.split('/')),
                                os.path.join(proj, os.path.basename(m.name))):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with open(dst, 'wb') as f:
                            f.write(blob)
                    n += 1
            return '3-D models: %d files of %s %s from %s' % (n, library_dir, sha[:9], lib)
    raise ModelLibraryError('no %s checkout has commit %s (looked in %s)' % (library_dir, sha, ', '.join(cands)))
