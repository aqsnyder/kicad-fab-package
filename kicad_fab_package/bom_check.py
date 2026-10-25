"""Regenerate the grouped BOM csv of a commit with a fixed kicad-cli command, and compare it with a committed one.

usage: kicad-bom-check [REV] [--repo DIR] [--csv PATH | --against FILE] [--out DIR] [--perref]
                       [--kicad-cli PATH] [--project-dir DIR] [--config FILE]

REV     commit (default HEAD); the schematic comes from a git-archive project copy (as kicad-project-copy makes), the
        committed csv from `git show REV:<csv>`. Nothing in the repo is written.
--csv   the committed BOM, repo-relative (default: the config file's bom_csv). With none of --csv, --against and
        bom_csv, nothing is compared and --out is required (export only).
--against FILE  compare with a local csv instead of the committed one (e.g. kicad-macrofab-bom output before it is
        committed)
--out   keep the outputs there: <rev>.grouped.csv (and <rev>.perref.csv with --perref)
--perref  also export one line per reference (for kicad-bomdiff)

The grouped command is
  kicad-cli sch export bom --fields 'Reference,${QUANTITY},Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}'
    --labels 'Reference,Qty,Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,DNP'
    --group-by 'Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}'
    -o <csv> <project>.kicad_sch
Field names are case-sensitive (a schematic using 'Tempco' gets an empty TempCo column). kicad-macrofab-bom writes
the same file with the same command.
kicad-cli 10.0.7 drops excluded-from-BOM symbols from every BOM export (--include-excluded-from-bom has no effect). DNP
alone does not drop a symbol: a DNP symbol still in the BOM is exported with its DNP column set (--exclude-dnp drops
it). Parts that are excluded from the BOM (test points, programming headers, DNP parts that are also excluded) are
therefore in neither csv; the MacroFab xlsx adds them as Populate 0 rows.
The comparison ignores CR (a working copy may be CRLF, the blobs LF). Exit 0 identical, 1 different, 2 error.
"""
import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from . import config, kproject
except ImportError:  # imported as a plain module from its folder
    import config  # noqa: F401
    import kproject  # noqa: F401

GROUPED = ['--fields', 'Reference,${QUANTITY},Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}',
           '--labels', 'Reference,Qty,Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,DNP',
           '--group-by', 'Value,Footprint,MPN,Voltage,Type,Tolerance,TempCo,${DNP}']
PERREF = ['--fields', 'Reference,Value,Footprint,MPN,Manufacturer,Voltage,Type,Tolerance,TempCo,${DNP},'
                      '${EXCLUDE_FROM_BOM},${EXCLUDE_FROM_BOARD}',
          '--labels', 'Reference,Value,Footprint,MPN,Manufacturer,Voltage,Type,Tolerance,TempCo,DNP,ExclBOM,ExclBoard',
          '--group-by', '']


def export(cli, sch, out, args):
    cmd = [cli, 'sch', 'export', 'bom'] + args + ['-o', out, sch]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 or not os.path.exists(out):
        raise kproject.ProjectError('BOM export failed:\n%s\n%s' % (r.stdout, r.stderr))
    return cmd


CONFIG_KEYS = ('project_dir', 'require_dru', 'kicad_cli')


def build_parser():
    ap = argparse.ArgumentParser(prog='kicad-bom-check', description=config.cli_description(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rev', nargs='?', default='HEAD', metavar='REV', help='the commit (default: HEAD)')
    ap.add_argument('--repo', default='.', metavar='DIR', help='the git repository (default: the current folder)')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--csv', dest='bom_csv', metavar='PATH', help='the committed grouped BOM csv, repo-relative, '
                                                                 "read at REV (config key bom_csv)")
    g.add_argument('--against', metavar='FILE', help='compare with this local csv instead of a committed one')
    ap.add_argument('--out', metavar='DIR', help='keep the regenerated csv(s) here as <rev>.grouped.csv '
                                                 '(and <rev>.perref.csv)')
    ap.add_argument('--perref', action='store_true', help='also export one line per reference (input of '
                                                          'kicad-bomdiff)')
    config.add_args(ap, CONFIG_KEYS)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    a = build_parser().parse_args(argv)
    tmp = tempfile.mkdtemp(prefix='bom_check_')
    try:
        s = config.resolve(a, a.repo)
        compare = bool(a.against or s.bom_csv)
        if not compare and not a.out:
            raise config.ConfigError('no BOM csv to compare with: pass --csv PATH (repo-relative) or --against FILE, '
                                     'or set bom_csv in the config file (or pass --out DIR to export only)')
        cli = kproject.kicad_cli(s.kicad_cli)
        info = kproject.build(os.path.join(tmp, 'proj'), a.repo, rev=a.rev, project_dir=s.project_dir, library='no',
                              require_dru=s.require_dru)
        sch = os.path.join(os.path.dirname(info['board']), info['name'] + '.kicad_sch')
        name = a.rev.replace('/', '_')
        grouped = os.path.join(tmp, name + '.grouped.csv')
        export(cli, sch, grouped, GROUPED)
        with open(grouped, 'rb') as f:
            got = f.read()
        y = got.replace(b'\r', b'').decode('utf-8-sig')
        if compare:
            if a.against:
                with open(a.against, 'rb') as f:
                    committed = f.read()
                what = a.against
            else:
                committed = kproject.git(a.repo, 'show', '%s:%s' % (info['sha'], s.bom_csv), binary=True)
                what = 'the committed csv'
            try:
                x = committed.replace(b'\r', b'').decode('utf-8-sig')
            except UnicodeDecodeError as e:
                raise kproject.ProjectError('%s is not a UTF-8 csv (%s)' % (config.show_path(what), e)) from None
            print(f"rev {a.rev} = {info['sha'][:9]}: regenerated {y.count(chr(10))} lines, "
                  f"{'local' if a.against else 'committed'} {x.count(chr(10))} lines")
        else:
            print(f"rev {a.rev} = {info['sha'][:9]}: regenerated {y.count(chr(10))} lines (no csv to compare with: "
                  f"export only)")
        if a.perref:
            export(cli, sch, os.path.join(tmp, name + '.perref.csv'), PERREF)
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            for f in os.listdir(tmp):
                if f.endswith('.csv'):
                    shutil.copyfile(os.path.join(tmp, f), os.path.join(a.out, f))
            print('outputs in', config.show_path(a.out))
        if not compare:
            rc = 0
        elif x == y:
            print(f'BOM: identical to {what} (CR ignored)')
            rc = 0
        else:
            d = list(difflib.unified_diff(x.splitlines(), y.splitlines(), 'local' if a.against else 'committed',
                                          'regenerated', n=0, lineterm=''))
            print('BOM: DIFFERS from %s: %d changed lines' % (
                what, sum(1 for l in d if l[:1] in '+-' and l[:3] not in ('+++', '---'))))
            for l in d[:60]:
                print('   ', l[:200])
            rc = 1
    except (kproject.ProjectError, config.ConfigError, OSError) as e:
        print('ERROR:', e)
        rc = 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
