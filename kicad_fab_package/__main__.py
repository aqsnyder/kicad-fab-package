"""`python -m kicad_fab_package [COMMAND ARGS...]`: run one of the tools, or list them."""
import importlib
import sys

from . import COMMANDS, __version__


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    names = {cmd: mod for cmd, mod in COMMANDS}
    names.update({mod: mod for _, mod in COMMANDS})
    if not argv or argv[0] in ('-h', '--help') or argv[0] not in names:
        print('kicad-fab-package %s\n\nusage: python -m kicad_fab_package COMMAND [ARGS...]\n\ncommands:' % __version__)
        for cmd, mod in COMMANDS:
            print('  %-20s (module %s)' % (cmd, mod))
        return 0 if not argv or argv[0] in ('-h', '--help') else 2
    mod = importlib.import_module('kicad_fab_package.' + names[argv[0]])
    return mod.main(argv[1:])


if __name__ == '__main__':
    sys.exit(main())
