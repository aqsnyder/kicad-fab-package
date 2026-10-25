"""Test helpers."""
import gc
import os
import shutil
import stat
import sys


def _retry_writable(func, path, *_):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def rmtree(path):
    """Remove a temporary tree, including read-only files (git marks its objects read-only on Windows), retrying
    once after a garbage collection in case an object not yet collected still holds a file open."""
    for _ in range(2):
        if not os.path.exists(path):
            return
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_retry_writable)
        else:
            shutil.rmtree(path, onerror=_retry_writable)
        gc.collect()
