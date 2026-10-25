"""Per-reference BOM diff of two per-reference csv exports (kicad-bom-check --perref).

Columns used: Reference, Value, Footprint, MPN, Manufacturer, Voltage, Type, Tolerance, TempCo, DNP, ExclBOM,
ExclBoard. A column is compared only when both files have it (a csv's 'Tempco' column is read as TempCo); the
columns only one file has are named in a NOTE line, so an older export without Manufacturer does not report every
reference as changed. Prints references ADDED / REMOVED (value, footprint, MPN, DNP) and, for references on both
sides, every compared field that CHANGED. Use it to explain a grouped-BOM change line by line, e.g. one release
against the next. Exit 0 when the comparison ran (whatever it found), 2 when a file cannot be read, has no
Reference column or is a grouped BOM (references such as C6,C7).
"""
import argparse
import csv
import re
import sys

KEYS = ['Value', 'Footprint', 'MPN', 'Manufacturer', 'Voltage', 'Type', 'Tolerance', 'TempCo', 'DNP', 'ExclBOM',
        'ExclBoard']


PERREF_HINT = 'kicad-bomdiff reads per-reference csvs, as `kicad-bom-check REV --perref --out DIR` writes them'


class BomDiffError(Exception):
    pass


def load(p):
    """(rows by Reference, set of column names), with an older 'Tempco' label read as TempCo. Raises BomDiffError
    for a file that cannot be read or has no Reference column."""
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
            if 'Reference' not in cols:
                raise BomDiffError('%s: no Reference column (columns: %s); %s'
                                   % (p, ', '.join(reader.fieldnames or []) or 'none, the file is empty', PERREF_HINT))
            rows = {r['Reference']: r for r in reader}
            grouped = [r for r in rows if ',' in (r or '')]
            if grouped:
                raise BomDiffError('%s: a grouped BOM (Reference %r); %s' % (p, grouped[0], PERREF_HINT))
    except FileNotFoundError:
        raise BomDiffError('%s: file not found' % p) from None
    except UnicodeDecodeError as e:
        raise BomDiffError('%s: not a UTF-8 csv (%s)' % (p, e)) from None
    except (OSError, csv.Error) as e:
        raise BomDiffError('%s: cannot read it (%s)' % (p, e)) from None
    if 'TempCo' not in cols and 'Tempco' in cols:
        cols.add('TempCo')
        for r in rows.values():
            r['TempCo'] = r['Tempco']
    return rows, cols


def sortkey(r):
    m = re.match(r'([A-Za-z#]+)(\d+)', r)
    return (m.group(1), int(m.group(2))) if m else (r, 0)


def compare(a, ca, b, cb):
    """{'keys', 'only_a', 'only_b', 'added', 'removed', 'changed'} for two load() results."""
    keys = [k for k in KEYS if k in ca and k in cb]
    changed = []
    for r in sorted(set(a) & set(b), key=sortkey):
        d = [(k, a[r].get(k, ''), b[r].get(k, '')) for k in keys if a[r].get(k, '') != b[r].get(k, '')]
        if d:
            changed.append((r, d))
    return {'keys': keys,
            'only_a': [k for k in KEYS if k in ca and k not in cb],
            'only_b': [k for k in KEYS if k in cb and k not in ca],
            'added': sorted(set(b) - set(a), key=sortkey),
            'removed': sorted(set(a) - set(b), key=sortkey),
            'changed': changed}


def build_parser():
    ap = argparse.ArgumentParser(prog='kicad-bomdiff', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a', metavar='A.perref.csv', help='the older per-reference BOM csv')
    ap.add_argument('b', metavar='B.perref.csv', help='the newer per-reference BOM csv')
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:          # --help: 0, a usage error: 2 (returned, so main() never raises)
        return e.code
    try:
        (a, ca), (b, cb) = load(args.a), load(args.b)
    except BomDiffError as e:
        print('ERROR:', e)
        return 2
    c = compare(a, ca, b, cb)
    only_a, only_b = c['only_a'], c['only_b']
    print('refs A=%d B=%d' % (len(a), len(b)))
    if only_a or only_b:
        print('NOTE: not compared, column missing on one side: %s' % '; '.join(
            x for x in ('only in A: ' + ', '.join(only_a) if only_a else '',
                        'only in B: ' + ', '.join(only_b) if only_b else '') if x))
    print('ADDED (%d):' % len(c['added']))
    for r in c['added']:
        x = b[r]
        print(('  + %-6s %-10s %-34s %-24s %s %s' % (r, x.get('Value'), x.get('Footprint'), x.get('MPN'), x.get('DNP'),
                                                    x.get('ExclBOM', ''))).rstrip())
    print('REMOVED (%d):' % len(c['removed']))
    for r in c['removed']:
        x = a[r]
        print(('  - %-6s %-10s %-34s %-24s %s' % (r, x.get('Value'), x.get('Footprint'), x.get('MPN'),
                                                 x.get('DNP'))).rstrip())
    print('CHANGED (%d):' % len(c['changed']))
    for r, d in c['changed']:
        print('  ~ %-6s ' % r + '; '.join('%s: %r -> %r' % t for t in d))
    return 0


if __name__ == '__main__':
    sys.exit(main())
