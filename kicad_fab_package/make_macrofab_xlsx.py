"""Build the MacroFab per-designator BOM xlsx of a commit, plus the grouped and per-reference BOM csvs, an optional
per-designator diff against a baseline BOM xlsx and a checks report.

usage: kicad-macrofab-bom [REV] --out DIR [--repo DIR] [--project-dir DIR] [--name NAME] [--name-template T]
                          [--baseline SPEC | --no-baseline] [--baseline-label LABEL] [--revision-label T]
                          [--non-part-refs RE] [--non-part-libs L1,L2] [--expect-fitted N]
                          [--expect-unfitted REFS] [--work DIR] [--kicad-cli PATH] [--config FILE]

REV        commit (default HEAD). The project is a git-archive copy (as kicad-project-copy makes) in a temp dir (or
           --work); nothing in the repo is read from the working tree or written.
--out      output directory (the package's bom/ folder), created if needed. NAME defaults to the name template
           ('{project}_v{revision}': the KiCad project name and the project's REVISION text variable, e.g.
           myboard_v1.2). Files:
             NAME_macrofab.xlsx    the BOM to upload to MacroFab (layout below)
             NAME_bom.csv          grouped BOM, the exact kicad-bom-check command
             NAME_bom_perref.csv   one line per BOM reference, kicad-bom-check --perref (input of kicad-bomdiff)
             NAME_vs_LABEL.md      per-designator diff of the xlsx against the baseline (LABEL: --baseline-label)
             NAME_bom_checks.md    sources, row rules, counts, schematic/board cross-check, string-hygiene flags
--baseline SPEC  BOM xlsx to diff against: REV:PATH (git show in --repo) or a local file. Default: the first of the
           config file's baseline_paths (project-relative) that exists at REV; it is an error when baseline_paths is
           set and none exists. With neither, there is no diff. Its Designator, Value, Footprint, Populate and first
           MPN / Manufacturer are compared.
--baseline-label LABEL  how the reports and the diff file name call the baseline (default 'baseline'; e.g. v1.1)
--revision-label T      how the diff report calls the new build: {project}, {revision} (default 'v{revision}'; NAME
                        when there is no revision)
--no-baseline           skip the diff
--expect-fitted N       fail unless exactly N rows have Populate 1
--expect-unfitted REFS  fail unless the Populate 0 designators are exactly REFS (comma list; ranges like TP1-TP8)
--work DIR              keep the project copy and the intermediate exports there (an empty or new directory)

xlsx layout (MacroFab: .xlsx, one sheet, header in row 1, one unique designator per row), with no alternate MPN /
Manufacturer pair; alternates are handled in MacroFab's sourcing tool.
  Designator | Value | Footprint | Populate | MPN | Manufacturer
Rows, in natural designator order (C1, C2, ..., C10):
  - one per schematic symbol whose footprint is on the board;
  - Populate 1: in the BOM (not DNP, not excluded from the BOM);
  - Populate 0: DNP or excluded from the BOM (test points, programming-header footprints, the DNP parts). kicad-cli
    10.0.7 drops excluded-from-BOM symbols from every BOM export (--include-excluded-from-bom has no effect). DNP
    alone does not drop a symbol: a DNP symbol that is in the BOM is exported with its DNP column set (--exclude-dnp
    drops it). Give every DNP part Exclude from BOM too, so every Populate 0 row comes from the kicadxml netlist. The
    script stops (exit 1) on a DNP part that is still in the BOM, because the grouped csv and kicad-fab-export's
    Populate 1 check expect DNP parts outside the BOM. A DNP part keeps its MPN;
  - no row: fiducials and mounting holes (Populate 0, no MPN, and a designator matching --non-part-refs or a
    footprint library in --non-part-libs; by default FID* / H* or KiCad's Fiducial / MountingHole libraries: not
    parts; kicad-fab-export leaves the same ones out of the XYRS), board-only footprints with no symbol (logos),
    symbols excluded from the board.
  The XYRS placement file must carry the same designators: an XYRS upload deletes BOM rows it does not contain.
Fields: MPN from the MPN field (never the lib_id: a library symbol's name often carries a different suffix);
  Manufacturer from Manufacturer, else MANUFACTURER; Footprint without the library prefix. Leading and trailing
  whitespace is stripped and reported; nothing else is changed. Commas, slashes or other odd characters in MPNs (each
  compared with the baseline), MF- house parts, manufacturer-name variants, DNP / DNM inside a fitted part's Value or
  MPN, and value+package collisions, and value+package groups that mix fitted and Populate 0 rows, are flagged in
  NAME_bom_checks.md.
xlsx encoding: text cells are shared strings (xl/sharedStrings.xml) and empty fields are absent cells, as in an xlsx
  that MacroFab exports; openpyxl 3.1 itself writes inline strings and empty inline cells.
A commit on no branch or tag (a scratch commit) is reported as a warning: its hash goes into the xlsx properties and
  the reports, so re-run on the final commit before committing the outputs.
Checks (exit 1 if one fails; the outputs are still written): schematic and board designator sets agree; per row, the
  sheet and the board footprint agree on footprint, Value, MPN, DNP and BOM flags; the BOM export agrees with the
  netlist; no Populate 1 row without an MPN; no unannotated or duplicate designator; --expect-fitted/--expect-unfitted.
The xlsx is byte-reproducible for a commit and an openpyxl version: zip timestamps and document dates are the commit
  date, and openpyxl writes with Python's own XML writer, not lxml, whether or not lxml is installed (the tool sets
  OPENPYXL_LXML=False when it is unset; OPENPYXL_LXML=True brings lxml back: the same cells, different bytes).
Needs openpyxl. Exit 0 OK, 1 a check failed, 2 setup error.
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

try:
    from . import bom_check, config, kproject, sexp
except ImportError:  # imported as a plain module from its folder
    import bom_check  # noqa: F401
    import config  # noqa: F401
    import kproject  # noqa: F401
    import sexp  # noqa: F401

# openpyxl writes through lxml when lxml is installed, and its lxml and standard-library writers serialize the same
# workbook to different bytes (same cells). Pick the standard-library writer unless OPENPYXL_LXML is already set, so the
# xlsx of a commit has the same bytes with or without lxml. openpyxl reads the variable once, on its first import.
os.environ.setdefault('OPENPYXL_LXML', 'False')

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter
except ImportError:  # reported in main()
    openpyxl = None

TOOL = 'make_macrofab_xlsx.py'
COLUMNS = ['Designator', 'Value', 'Footprint', 'Populate', 'MPN', 'Manufacturer']
# the BOM rows (Populate 1) as kicad-cli exports them; DNP / ExclBOM / ExclBoard are checked, not trusted
ROWS_EXPORT = ['--fields', 'Reference,Value,Footprint,MPN,Manufacturer,MANUFACTURER,${DNP},${EXCLUDE_FROM_BOM},'
                           '${EXCLUDE_FROM_BOARD}',
               '--labels', 'Reference,Value,Footprint,MPN,Manufacturer,MANUFACTURER,DNP,ExclBOM,ExclBoard',
               '--group-by', '', '--ref-range-delimiter', '']
# fiducials and mounting holes (the default non_part_libs / non_part_refs settings): the same rule as
# export_fab.is_non_part, so the BOM and the XYRS agree
NON_PART_LIBS = ('Fiducial', 'MountingHole')
NON_PART_RE = re.compile(r'^(FID|H)\d+$')
MPN_CHARS = re.compile(r'[A-Za-z0-9.\-+#_]')   # '/' is flagged: some vendors' MPNs carry it legitimately
# manufacturer names MacroFab's part library spells differently
KNOWN_RENAMES = {'cui devices': 'CUI Devices is now Same Sky; MacroFab lists Same Sky'}
# where the checks report sends the reader about BOM lines after the import (how MacroFab groups them is MacroFab's
# to change, so the report states no rule)
LINE_GROUPING = ('see "Line grouping and Populate", section 7 of the MacroFab walkthrough, docs/macrofab.md in '
                 'kicad-fab-package')
MFR_NOISE = {'inc', 'incorporated', 'corp', 'corporation', 'co', 'ltd', 'llc', 'limited', 'gmbh', 'ag', 'sa', 'plc',
             'group', 'company', 'technology', 'technologies', 'electronics', 'semiconductor', 'semiconductors',
             'components', 'international', 'intl', 'america', 'americas', 'usa', 'the'}


class Fail(Exception):
    pass


def natkey(ref):
    m = re.match(r'^([A-Za-z_#]*)(\d+)(.*)$', ref)
    return (m.group(1).upper(), int(m.group(2)), m.group(3)) if m else (ref.upper(), -1, '')


def expand_refs(spec):
    out = set()
    for part in (spec or '').split(','):
        part = part.strip()
        m = re.match(r'^([A-Za-z_]+)(\d+)-([A-Za-z_]*)(\d+)$', part)
        if m and m.group(3) in ('', m.group(1)) and int(m.group(2)) <= int(m.group(4)):
            out.update('%s%d' % (m.group(1), i) for i in range(int(m.group(2)), int(m.group(4)) + 1))
        elif part:
            out.add(part)
    return out


def compress_refs(refs):
    """C1,C2,C3,C7 -> C1-C3, C7 (for the reports only)."""
    out, run = [], []
    for r in sorted(refs, key=natkey):
        k = natkey(r)
        last = natkey(run[-1]) if run else None
        if last and k[2] == '' and last[2] == '' and k[0] == last[0] and k[1] == last[1] + 1:
            run.append(r)
            continue
        if run:
            out.append(run[0] if len(run) == 1 else '%s-%s' % (run[0], run[-1]))
        run = [r]
    if run:
        out.append(run[0] if len(run) == 1 else '%s-%s' % (run[0], run[-1]))
    return ', '.join(out)


def fp_name(lib_id):
    return lib_id.split(':', 1)[-1]


def fp_lib(lib_id):
    return lib_id.split(':', 1)[0] if ':' in lib_id else ''


def unq(tok):
    if isinstance(tok, str) and len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t', 'r': '\r'}.get(m.group(1), m.group(1)), tok[1:-1])
    return tok


def md(v):
    s = '' if v is None else str(v)
    return s.replace('|', '\\|').replace('\n', ' ') if s else ''


def shell_quote(arg):
    return "'%s'" % arg if re.search(r"[\s$,{}()|;&'\"]", arg) or arg == '' else arg


# ---------------------------------------------------------------- sources

def board_footprints(path):
    """Every footprint of a .kicad_pcb: ref, lib id, layer, Value, MPN, Manufacturer, attribute tokens."""
    text = sexp.read_text(path)
    # top-level footprints only (one tab deep, as KiCad writes them); parsing every zone fill would take far longer
    nodes = [sexp.parse_span(text, m.start() + 1)[0] for m in re.finditer(r'^\t\(footprint ', text, re.M)]
    if not nodes:
        nodes = [it['node'] for it in sexp.parse_top(text) if it['head'] == 'footprint']
    out = []
    for n in nodes:
        props = {}
        for p in sexp.getall(n, 'property'):
            if len(p) > 2 and not isinstance(p[2], list):
                props[unq(p[1])] = unq(p[2])
        attr = sexp.get(n, 'attr')
        layer = sexp.get(n, 'layer')
        out.append({'ref': props.get('Reference', ''), 'lib': unq(n[1]), 'layer': unq(layer[1]) if layer else '',
                    'value': props.get('Value', ''), 'mpn': props.get('MPN', ''),
                    'attrs': {x for x in attr[1:] if not isinstance(x, list)} if attr else set()})
    return out


def netlist_comps(path):
    """kicadxml netlist: every symbol (not only the BOM ones) with its fields and DNP / BOM / board flags."""
    root = ET.parse(path).getroot()
    comps, dups = {}, []
    for c in root.iter('comp'):
        ref = c.get('ref')
        fields = {}
        fe = c.find('fields')
        if fe is not None:
            for f in fe.findall('field'):
                fields[f.get('name')] = f.text or ''
        props = {p.get('name') for p in c.findall('property')}
        if ref in comps:
            dups.append(ref)
        comps[ref] = {'ref': ref, 'value': c.findtext('value') or '', 'footprint': c.findtext('footprint') or '',
                      'fields': fields, 'dnp': 'dnp' in props, 'excl_bom': 'exclude_from_bom' in props,
                      'excl_board': 'exclude_from_board' in props}
    return comps, dups


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def kicad_version(cli):
    r = subprocess.run([cli, 'version'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.stdout.strip() or 'unknown'


def project_revision(proj_dir, name, board):
    try:
        with open(os.path.join(proj_dir, name + '.kicad_pro'), encoding='utf-8') as f:
            v = json.load(f).get('text_variables', {}).get('REVISION')
        if v:
            return v
    except (OSError, ValueError):
        pass
    m = re.search(r'^\s*\(property "REVISION" "([^"]*)"', sexp.read_text(board), re.M)
    return m.group(1) if m else None


def load_baseline(spec, repo, sha, project_dir, candidates=()):
    """Returns (label, {designator: row}, alternates, duplicates), or (message, None, ...) when none of the
    candidates (project-relative paths, searched at sha when spec is None) exists, or (None, None, ...) when there is
    no spec and no candidate: no baseline is configured."""
    if spec is None:
        if not candidates:
            return None, None, [], []
        for p in candidates:
            path = kproject.under(project_dir.rstrip('/'), p)
            if subprocess.run(['git', '-C', repo, 'cat-file', '-e', '%s:%s' % (sha, path)],
                              capture_output=True).returncode == 0:
                spec = '%s:%s' % (sha, path)
                break
        else:
            return 'no baseline at %s (looked for %s)' % (sha[:9], ', '.join(candidates)), None, [], []
    if os.path.isfile(spec):
        with open(spec, 'rb') as f:
            data = f.read()
    else:
        rev, _, path = spec.partition(':')
        data = kproject.git(repo, 'show', '%s:%s' % (rev, path), binary=True)
    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h).strip().lower() if h is not None else '' for h in rows[0]]

    def cols(n):
        return [i for i, h in enumerate(hdr) if h == n]

    i_d, i_v, i_f, i_p = (cols(n)[0] if cols(n) else None for n in ('designator', 'value', 'footprint', 'populate'))
    i_mpn, i_man = cols('mpn'), cols('manufacturer')
    if i_d is None or not i_mpn:
        raise Fail('baseline %s: no Designator / MPN header in row 1' % spec)

    def cell(r, i):
        if i is None or i >= len(r) or r[i] is None:
            return ''
        v = r[i]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).strip()

    out, alts, dups = {}, [], []
    for r in rows[1:]:
        d = cell(r, i_d)
        if not d:
            continue
        if d in out:
            dups.append(d)
        p = cell(r, i_p).lower()
        pop = 1 if p in ('1', 'true', 'yes', 'y') else 0 if p in ('0', 'false', 'no', 'n') else p
        out[d] = {'Designator': d, 'Value': cell(r, i_v), 'Footprint': cell(r, i_f), 'Populate': pop,
                  'MPN': cell(r, i_mpn[0]), 'Manufacturer': cell(r, i_man[0]) if i_man else ''}
        for j, c in enumerate(i_mpn[1:], 1):
            if cell(r, c):
                alts.append((d, cell(r, c), cell(r, i_man[j]) if j < len(i_man) else ''))
    return spec, out, alts, dups


# ---------------------------------------------------------------- rows and checks

def build_rows(bom_rows, comps, net_dups, fps, baseline_label=None, non_part_refs=NON_PART_RE,
               non_part_libs=NON_PART_LIBS):
    """The xlsx rows plus everything the reports need. Errors are collected, not raised. baseline_label only
    words the reason given for fiducials and mounting holes having no row (None: no baseline is configured, so the
    reason does not mention one). non_part_refs (a compiled regex matched from the start, or None) and non_part_libs
    (footprint library names) recognise those fiducials and mounting holes."""
    errors, stripped, fallback, omitted = [], [], [], []

    def clean(ref, col, v):
        v = v or ''
        if v.strip() != v:
            stripped.append((ref, col, v))
        return v.strip()

    for d in net_dups:
        errors.append('duplicate designator %s in the netlist' % d)
    for ref in comps:
        if '?' in ref:
            errors.append('unannotated symbol %s' % ref)

    bom = {}
    for r in bom_rows:
        ref = r['Reference'].strip()
        if ref in bom:
            errors.append('duplicate designator %s in the BOM export' % ref)
        bom[ref] = r
        if r.get('DNP', '').strip():
            errors.append('%s: DNP but still in the BOM (in_bom yes), so kicad-cli exports it with DNP set; give it '
                          'Exclude from BOM as well, like the other DNP parts (the grouped csv and kicad-fab-export '
                          'expect DNP parts outside the BOM)' % ref)
        if r.get('ExclBOM', '').strip():
            errors.append('%s: excluded from the BOM, yet the BOM export lists it (kicad-cli 10.0.7 drops such '
                          'symbols: a kicad-cli change?)' % ref)

    rows = {}
    for ref, c in sorted(comps.items(), key=lambda t: natkey(t[0])):
        f = c['fields']
        pop = 0 if (c['dnp'] or c['excl_bom']) else 1
        if c['excl_board']:
            omitted.append((ref, c['value'], 'excluded from the board (not placed by the assembler)'))
            continue
        if ref in bom:
            b = bom[ref]
            row = {'Value': clean(ref, 'Value', b['Value']), 'lib': clean(ref, 'Footprint', b['Footprint']),
                   'MPN': clean(ref, 'MPN', b['MPN'])}
            man, man_alt = b['Manufacturer'], b['MANUFACTURER']
            for k, nv in (('Value', c['value']), ('lib', c['footprint']), ('MPN', f.get('MPN', '')),
                          ('Manufacturer', f.get('Manufacturer', ''))):
                bv = row[k] if k != 'Manufacturer' else man.strip()
                if bv != (nv or '').strip():
                    errors.append('%s: %s differs between the BOM export (%r) and the netlist (%r); kicad-cli strips '
                                  'tabs and line breaks' % (ref, k, bv, nv))
        else:
            row = {'Value': clean(ref, 'Value', c['value']), 'lib': clean(ref, 'Footprint', c['footprint']),
                   'MPN': clean(ref, 'MPN', f.get('MPN', ''))}
            man, man_alt = f.get('Manufacturer', ''), f.get('MANUFACTURER', '')
            if pop == 1:
                errors.append('%s: in the BOM per its flags but missing from the BOM export' % ref)
        row['Manufacturer'] = clean(ref, 'Manufacturer', man)
        if not row['Manufacturer'] and (man_alt or '').strip():
            row['Manufacturer'] = clean(ref, 'MANUFACTURER', man_alt)
            fallback.append(ref)
        by_lib = fp_lib(row['lib']) in non_part_libs
        if pop == 0 and not row['MPN'] and (by_lib or (non_part_refs and non_part_refs.match(ref))):
            what = '%s footprint' % fp_lib(row['lib']) if by_lib else 'fiducial / mounting-hole designator'
            omitted.append((ref, row['Value'], '%s: not a part%s' % (
                what, ' (no row in the as-built %s BOM)' % baseline_label if baseline_label else '')))
            continue
        row.update({'Designator': ref, 'Footprint': fp_name(row['lib']), 'Populate': pop,
                    'flags': [k for k in ('dnp', 'excl_bom') if c[k]]})
        rows[ref] = row
    for ref in bom:
        if ref not in comps:
            errors.append('%s: in the BOM export but not in the netlist' % ref)
        elif comps[ref]['dnp'] or comps[ref]['excl_bom']:
            errors.append('%s: in the BOM export although DNP / excluded from the BOM' % ref)

    # schematic <-> board
    board, board_only, bdups = {}, [], []
    for fp in fps:
        if 'board_only' in fp['attrs']:
            board_only.append(fp)
            continue
        if fp['ref'] in board:
            bdups.append(fp['ref'])
        board[fp['ref']] = fp
    for d in bdups:
        errors.append('duplicate designator %s on the board' % d)
    for ref, c in comps.items():
        if not c['excl_board'] and ref not in board:
            errors.append('%s: symbol has no footprint on the board' % ref)
    for ref in board:
        if ref not in comps:
            errors.append('%s: footprint on the board has no symbol (not board-only)' % ref)
    side = collections.Counter()
    for ref, row in rows.items():
        fp = board.get(ref)
        if fp is None:
            continue
        side[(row['Populate'], fp['layer'])] += 1
        row['layer'] = fp['layer']
        row['through_hole'] = 'through_hole' in fp['attrs']
        checks = [('footprint', fp['lib'], row['lib']), ('Value', fp['value'].strip(), row['Value']),
                  ('MPN', fp['mpn'].strip(), row['MPN']),
                  ('DNP', 'dnp' in fp['attrs'], 'dnp' in row['flags']),
                  ('exclude_from_bom', 'exclude_from_bom' in fp['attrs'], 'excl_bom' in row['flags'])]
        for what, bv, sv in checks:
            if bv != sv:
                errors.append('%s: %s differs: board %r, schematic %r (Update PCB from Schematic?)'
                              % (ref, what, bv, sv))
        if 'exclude_from_pos_files' in fp['attrs']:
            errors.append('%s: footprint is excluded from position files, so the XYRS would lack it' % ref)
    for ref, row in rows.items():
        if row['Populate'] == 1 and not row['MPN']:
            errors.append('%s: Populate 1 without an MPN' % ref)
    out = [rows[r] for r in sorted(rows, key=natkey)]
    return out, {'errors': errors, 'stripped': stripped, 'fallback': fallback, 'omitted': omitted,
                 'board_only': board_only, 'side': side, 'board': board}


def mfr_key(name):
    w = re.sub(r'[^a-z0-9]+', ' ', name.lower().replace('&', ' and ')).split()
    return frozenset(x for x in w if x not in MFR_NOISE) or frozenset(w)


def hygiene(rows):
    """String-hygiene flags (nothing is changed)."""
    h = collections.OrderedDict()
    h['odd_mpn'] = [(r['Designator'], r['MPN'], ''.join(sorted({ch for ch in r['MPN'] if not MPN_CHARS.match(ch)})))
                    for r in rows if r['MPN'] and MPN_CHARS.sub('', r['MPN'])]
    h['non_ascii'] = [(r['Designator'], k, r[k]) for r in rows for k in ('Value', 'MPN', 'Manufacturer', 'Footprint')
                      if any(ord(ch) > 126 or ord(ch) < 32 for ch in r[k])]
    h['double_space'] = [(r['Designator'], k, r[k]) for r in rows for k in ('Value', 'MPN', 'Manufacturer')
                         if '  ' in r[k]]
    h['formula_like'] = [(r['Designator'], k, r[k]) for r in rows for k in ('Value', 'MPN', 'Manufacturer')
                         if r[k].startswith('=')]
    house = collections.defaultdict(list)
    for r in rows:
        if r['MPN'].upper().startswith('MF-'):
            house[(r['MPN'], r['Manufacturer'])].append(r['Designator'])
    h['house'] = sorted(house.items(), key=lambda t: t[0])
    h['dnp_text'] = [(r['Designator'], k, r[k]) for r in rows if r['Populate'] == 1
                     for k in ('Value', 'MPN', 'Footprint') if re.search(r'DN[PM]', r[k], re.I)]
    h['no_manufacturer'] = [(r['Designator'], r['MPN']) for r in rows if r['Populate'] == 1 and not r['Manufacturer']]
    h['pop0_no_mpn'] = [r['Designator'] for r in rows if r['Populate'] == 0 and not r['MPN']]
    # manufacturer names: counts, variant groups (same words once suffixes are dropped, or one a subset of the other)
    names = collections.Counter(r['Manufacturer'] for r in rows if r['Manufacturer'])
    parent = {n: n for n in names}

    def find(n):
        while parent[n] != n:
            n = parent[n]
        return n
    ns = sorted(names)
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            ka, kb = mfr_key(a), mfr_key(b)
            if ka <= kb or kb <= ka:
                parent[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for n in ns:
        groups[find(n)].append(n)
    h['mfr_names'] = sorted(names.items(), key=lambda t: (-t[1], t[0].lower()))
    h['mfr_variants'] = sorted([sorted(g) for g in groups.values() if len(g) > 1])
    h['mfr_known'] = [(n, KNOWN_RENAMES[n.lower()]) for n in ns if n.lower() in KNOWN_RENAMES]
    by_mpn = collections.defaultdict(set)
    for r in rows:
        if r['MPN']:
            by_mpn[r['MPN']].add(r['Manufacturer'])
    h['mpn_two_mfrs'] = sorted((m, sorted(s)) for m, s in by_mpn.items() if len(s) > 1)
    # fitted rows with the same Value + package but different MPNs: if a BOM line ever held them all, it would carry one
    # MPN for all of them (how MacroFab groups lines is its own to change: docs/macrofab.md section 7)
    grp = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        if r['Populate'] == 1:
            grp[(r['Value'], r['Footprint'])][r['MPN']].append(r['Designator'])
    h['collisions'] = sorted(((k, sorted(v.items(), key=lambda t: natkey(t[1][0])))
                              for k, v in grp.items() if len(v) > 1), key=lambda t: (t[0][1], t[0][0]))
    # Value + package groups that mix fitted and Populate 0 rows: if MacroFab's grouping carried one Populate for the
    # whole line, it would fit a DNP strap or drop fitted parts (e.g. 0R straps where only some are fitted)
    mix = collections.defaultdict(lambda: {0: [], 1: []})
    for r in rows:
        mix[(r['Value'], r['Footprint'])][r['Populate']].append(r['Designator'])
    h['mixed_populate'] = sorted(((k, sorted(v[1], key=natkey), sorted(v[0], key=natkey))
                                  for k, v in mix.items() if v[0] and v[1]), key=lambda t: (t[0][1], t[0][0]))
    return h


# ---------------------------------------------------------------- writers

def write_xlsx(path, rows, when, title, description):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Sheet1'
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal='center')
    for r in rows:
        ws.append([None if r[k] == '' else r[k] for k in COLUMNS])   # an empty field is no cell, not an empty one
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.data_type == 'f':  # a value starting with '=' is text here, never a formula
                c.data_type = 's'
    for i, k in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = max([len(k)] + [len(str(r[k])) for r in rows]) + 2
    p = wb.properties
    p.creator = 'make_macrofab_xlsx.py'
    p.title = title
    p.description = description
    p.created = p.modified = when
    buf = io.BytesIO()
    wb.save(buf)
    # openpyxl stamps dcterms:modified with the save time and the zip entries with the local time: pin both
    stamp = when.strftime('%Y-%m-%dT%H:%M:%SZ').encode()
    src = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    parts = collections.OrderedDict((info.filename, src.read(info.filename)) for info in src.infolist())
    attrs = {info.filename: info.external_attr for info in src.infolist()}
    parts = shared_strings(parts)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for fname, data in parts.items():
            if fname == 'docProps/core.xml':
                data = re.sub(rb'(<dcterms:modified\b[^>]*>)[^<]*(</dcterms:modified>)', rb'\g<1>' + stamp + rb'\g<2>',
                              data)
            zi = zipfile.ZipInfo(fname, date_time=when.timetuple()[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = attrs.get(fname, attrs.get('xl/worksheets/sheet1.xml', 0))
            z.writestr(zi, data)


SST_CT = b'application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml'
SST_REL = b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings'


def shared_strings(parts):
    """Rewrite openpyxl's inline-string cells (t="inlineStr" <is><t>..</t></is>) as shared strings (t="s" <v>n</v>
    plus xl/sharedStrings.xml, its content type and its workbook relationship): the layout Excel and MacroFab's own
    export uses. The escaped XML text is carried over byte for byte. Fails loudly on any
    inline cell it does not recognise."""
    cell_re = re.compile(rb'<c ([^>]*?)t="inlineStr"([^>]*)><is><t(?: xml:space="preserve")?>([^<]*)</t></is></c>')
    table, index = [], {}

    def repl(m):
        text = m.group(3)
        if text not in index:
            index[text] = len(table)
            table.append(text)
        return b'<c ' + m.group(1) + b't="s"' + m.group(2) + b'><v>%d</v></c>' % index[text]
    count = 0
    for name in [n for n in parts if n.startswith('xl/worksheets/') and n.endswith('.xml')]:
        data, n = cell_re.subn(repl, parts[name])
        if b'inlineStr' in data:
            raise Fail('%s: an inline-string cell the shared-string rewrite does not handle' % name)
        parts[name] = data
        count += n
    if not table:
        return parts
    sst = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/'
           b'spreadsheetml/2006/main" count="%d" uniqueCount="%d">' % (count, len(table)) +
           b''.join((b'<si><t xml:space="preserve">%s</t></si>' if t[:1].isspace() or t[-1:].isspace()
                     else b'<si><t>%s</t></si>') % t for t in table) + b'</sst>')
    ct = parts['[Content_Types].xml']
    parts['[Content_Types].xml'] = ct.replace(b'</Types>', b'<Override PartName="/xl/sharedStrings.xml" ContentType="'
                                              + SST_CT + b'"/></Types>')
    rels = parts['xl/_rels/workbook.xml.rels']
    ids = [int(x) for x in re.findall(rb'Id="rId(\d+)"', rels)]
    rid = b'rId%d' % (max(ids or [0]) + 1)
    parts['xl/_rels/workbook.xml.rels'] = rels.replace(
        b'</Relationships>', b'<Relationship Type="' + SST_REL + b'" Target="sharedStrings.xml" Id="' + rid +
        b'"/></Relationships>')
    out = collections.OrderedDict()
    for k, v in parts.items():       # sharedStrings.xml right after the worksheets
        out[k] = v
        if k.startswith('xl/worksheets/sheet'):
            out.setdefault('xl/sharedStrings.xml', sst)
    out.setdefault('xl/sharedStrings.xml', sst)
    return out


def norm_mpn(m):
    return re.sub(r'[\s\-]', '', m or '').upper()


def diff_md(name, rev_label, rows, base_label, base, alts, base_dups, label='baseline', new_label=None,
            generator=TOOL):
    """The per-designator diff report. label names the baseline in the text (e.g. v1.1), new_label the new
    build (default: name), generator the tool named in the 'Generated by' line."""
    new_label = new_label or name
    cur = {r['Designator']: r for r in rows}
    added = sorted(set(cur) - set(base), key=natkey)
    removed = sorted(set(base) - set(cur), key=natkey)
    changed = []
    counts = collections.Counter()
    for d in sorted(set(cur) & set(base), key=natkey):
        a, b = base[d], cur[d]
        cells, notes = {}, []
        for k in ('Populate', 'MPN', 'Manufacturer', 'Value', 'Footprint'):
            if str(a[k]) != str(b[k]):
                cells[k] = '%s -> %s' % (a[k] if a[k] != '' else '(empty)', b[k] if b[k] != '' else '(empty)')
                counts[k] += 1
        if not cells:
            continue
        if 'MPN' in cells and norm_mpn(a['MPN']) == norm_mpn(b['MPN']):
            notes.append('MPN format only')
            counts['MPN format only'] += 1
        if 'Manufacturer' in cells and 'MPN' not in cells:
            counts['Manufacturer only'] += 1
        if 'Value' in cells and 'Footprint' in cells:
            notes.append('value and footprint changed: designator reused?')
        changed.append((d, cells, notes))
    L = ['# %s BOM vs the as-built %s BOM' % (name, label), '',
         'Generated by `kicad-macrofab-bom` (`%s`); do not edit by hand.' % generator, '',
         '- New: `%s_macrofab.xlsx`, %s, %d rows (Populate 1: %d, Populate 0: %d).'
         % (name, rev_label, len(rows), sum(r['Populate'] == 1 for r in rows), sum(r['Populate'] == 0 for r in rows)),
         '- Baseline: `%s`, %d designators (Populate 1: %d, Populate 0: %d).'
         % (base_label, len(base), sum(r['Populate'] == 1 for r in base.values()),
            sum(r['Populate'] == 0 for r in base.values())),
         '- Compared per designator: Populate, MPN, Manufacturer (the baseline\'s first pair), Value, Footprint. '
         '"MPN format only" means equal once case, spaces and hyphens are ignored.', '',
         '## Summary', '', '| | Designators |', '|---|---|',
         '| In both | %d |' % len(set(cur) & set(base)),
         '| Added (new designators) | %d |' % len(added), '| Removed | %d |' % len(removed),
         '| Changed (any field) | %d |' % len(changed),
         '| - MPN changed | %d (format only: %d) |' % (counts['MPN'], counts['MPN format only']),
         '| - Manufacturer changed, MPN unchanged | %d |' % counts['Manufacturer only'],
         '| - Manufacturer changed (all) | %d |' % counts['Manufacturer'],
         '| - Populate changed | %d |' % counts['Populate'],
         '| - Value changed | %d |' % counts['Value'], '| - Footprint changed | %d |' % counts['Footprint'], '']
    if base_dups:
        L += ['Baseline duplicate designators (last row kept): %s' % ', '.join(base_dups), '']
    L += ['## Added (%d)' % len(added), '']
    if added:
        L += ['| Designator | Value | Footprint | Populate | MPN | Manufacturer |', '|---|---|---|---|---|---|']
        L += ['| %s | %s | %s | %s | %s | %s |' % tuple(md(cur[d][k]) for k in COLUMNS) for d in added]
    else:
        L.append('None.')
    L += ['', '## Removed (%d)' % len(removed), '']
    if removed:
        L += ['| Designator | Value | Footprint | Populate | MPN | Manufacturer |', '|---|---|---|---|---|---|']
        L += ['| %s | %s | %s | %s | %s | %s |' % tuple(md(base[d][k]) for k in COLUMNS) for d in removed]
    else:
        L.append('None.')
    L += ['', '## Changed (%d)' % len(changed), '',
          'Only the changed fields are filled (%s -> %s).' % (label, new_label), '',
          '| Designator | Populate | MPN | Manufacturer | Value | Footprint | Note |', '|---|---|---|---|---|---|---|']
    for d, cells, notes in changed:
        L.append('| %s | %s | %s | %s | %s | %s | %s |' % (
            d, *(md(cells.get(k, '')) for k in ('Populate', 'MPN', 'Manufacturer', 'Value', 'Footprint')),
            md('; '.join(notes))))
    # MPN level (fitted rows): new to the build, and no longer used
    base_all = {norm_mpn(r['MPN']) for r in base.values() if r['MPN']} | {norm_mpn(m) for _, m, _ in alts}
    cur_all = {norm_mpn(r['MPN']) for r in rows if r['MPN']}
    new = collections.defaultdict(list)
    for r in rows:
        if r['Populate'] == 1 and r['MPN'] and norm_mpn(r['MPN']) not in base_all:
            new[(r['MPN'], r['Manufacturer'])].append(r['Designator'])
    gone = collections.defaultdict(list)
    for r in base.values():
        if r['Populate'] == 1 and r['MPN'] and norm_mpn(r['MPN']) not in cur_all:
            gone[(r['MPN'], r['Manufacturer'])].append(r['Designator'])
    L += ['', '## MPNs on fitted rows that the %s BOM does not have (%d)' % (label, len(new)), '',
          'Stock-check these first: they were never bought for this board.', '']
    if new:
        L += ['| MPN | Manufacturer | Designators |', '|---|---|---|']
        L += ['| %s | %s | %s |' % (md(m), md(mf), compress_refs(v))
              for (m, mf), v in sorted(new.items(), key=lambda t: natkey(sorted(t[1], key=natkey)[0]))]
    else:
        L.append('None.')
    L += ['', '## %s fitted MPNs no longer on the BOM (%d)' % (label, len(gone)), '']
    if gone:
        L += ['| MPN | Manufacturer | %s designators |' % label, '|---|---|---|']
        L += ['| %s | %s | %s |' % (md(m), md(mf), compress_refs(v))
              for (m, mf), v in sorted(gone.items(), key=lambda t: natkey(sorted(t[1], key=natkey)[0]))]
    else:
        L.append('None.')
    L += ['', '## %s alternates' % label, '']
    if alts:
        L += ['The baseline had these second MPN / Manufacturer entries; the %s xlsx has no alternate columns.'
              % new_label, '',
              '| Designator | MPN | Manufacturer |', '|---|---|---|']
        L += ['| %s | %s | %s |' % (d, md(m), md(mf)) for d, m, mf in sorted(alts, key=lambda t: natkey(t[0]))]
    else:
        L.append('None: the baseline\'s second MPN / Manufacturer columns are empty on every row.')
    return '\n'.join(L) + '\n', {'added': added, 'removed': removed, 'changed': len(changed), 'counts': counts}


def checks_md(name, rev_label, cli_version, cmds, rows, res, h, expect_lines, base=None, refs=None,
              label=None, generator=TOOL):
    """The build record and checks report. label names the baseline in the text (None: no baseline is configured,
    so the row rules do not mention one), generator the tool named in the 'Generated by' line."""
    pop1 = [r for r in rows if r['Populate'] == 1]
    pop0 = [r for r in rows if r['Populate'] == 0]
    side = res['side']
    L = ['# %s MacroFab BOM: build record and checks' % name, '',
         'Generated by `kicad-macrofab-bom` (`%s`); do not edit by hand.' % generator, '',
         '## Source', '', '- %s' % rev_label]
    if refs is not None and not refs:
        L.append('- **Warning: this commit is on no branch or tag** (a scratch commit). Re-run on the final commit '
                 'before these files are committed.')
    L += ['- kicad-cli %s, on a `git archive` project copy (as `kicad-project-copy --rev` makes).' % cli_version,
          '- Commands (`<sch>` = the copy\'s root schematic):', '']
    L += ['```'] + cmds + ['```', '']
    L += ['## Row rules', '',
          '- One row per schematic symbol whose footprint is on the board, natural designator order.',
          '- Populate 1: in the BOM. Populate 0: DNP or excluded from the BOM. kicad-cli 10.0.7 drops '
          'excluded-from-BOM symbols from its BOM exports; a DNP symbol still in the BOM would be exported with DNP '
          'set (kicad-macrofab-bom stops on one). Every DNP part here is also excluded from the BOM, so the '
          'Populate 0 rows come from the kicadxml netlist. DNP rows keep their MPN.',
          '- No row: fiducials and mounting holes (not parts%s), board-only footprints '
          'without a symbol, symbols excluded from the board. The XYRS must carry exactly the same designators.'
          % ('; the as-built %s BOM has none' % label if label else ''),
          '- MPN from the MPN field, never the lib_id. Manufacturer from Manufacturer, else MANUFACTURER. Footprint '
          'without the library prefix. Whitespace stripped (listed below); nothing else changed.', '',
          '## Counts', '',
          '| | Rows | F.Cu | B.Cu |', '|---|---|---|---|',
          '| Populate 1 | %d | %d | %d |' % (len(pop1), side[(1, 'F.Cu')], side[(1, 'B.Cu')]),
          '| Populate 0 | %d | %d | %d |' % (len(pop0), side[(0, 'F.Cu')], side[(0, 'B.Cu')]),
          '| All rows | %d | %d | %d |' % (len(rows), side[(1, 'F.Cu')] + side[(0, 'F.Cu')],
                                            side[(1, 'B.Cu')] + side[(0, 'B.Cu')]), '',
          'Through-hole rows (XYRS type 2): %s.'
          % (compress_refs(r['Designator'] for r in rows if r.get('through_hole')) or 'none'), '',
          '### Populate 0 (%d)' % len(pop0), '',
          '| Designator | Why | Value | Footprint | MPN |', '|---|---|---|---|---|']
    for r in pop0:
        why = 'DNP' if 'dnp' in r['flags'] else 'excluded from BOM'
        L.append('| %s | %s | %s | %s | %s |'
                 % (r['Designator'], why, md(r['Value']), md(r['Footprint']), md(r['MPN'])))
    L += ['', '### No row (%d symbols, %d board-only footprints)' % (len(res['omitted']), len(res['board_only'])), '',
          '| Designator | Value | Side | Reason |', '|---|---|---|---|']
    for ref, val, why in sorted(res['omitted'], key=lambda t: natkey(t[0])):
        fp = res['board'].get(ref)
        L.append('| %s | %s | %s | %s |' % (ref, md(val), fp['layer'] if fp else '', md(why)))
    only = collections.Counter((fp['ref'], fp['value'], fp['layer'], fp_name(fp['lib'])) for fp in res['board_only'])
    for (ref, val, layer, fpn), n in sorted(only.items(), key=lambda t: (natkey(t[0][0]), t[0][2], t[0][3])):
        L.append('| %s | %s | %s | board-only footprint %s, no symbol%s |' % (md(ref), md(val), layer, md(fpn),
                                                                             ' (x%d)' % n if n > 1 else ''))
    L += ['', '## Checks', '']
    if res['errors'] or expect_lines and any(x.startswith('FAIL') for x in expect_lines):
        L.append('**FAILED** (%d):' % (len(res['errors']) + sum(x.startswith('FAIL') for x in expect_lines)))
        L.append('')
        L += ['- %s' % md(e) for e in res['errors']]
    else:
        L.append('All passed: schematic and board designator sets agree; per row, the sheet and the board footprint '
                 'agree on footprint, Value, MPN, DNP and BOM flags; the BOM export agrees with the netlist; every '
                 'Populate 1 row has an MPN; no unannotated or duplicate designator.')
    L += ['- %s' % x for x in expect_lines]
    L += ['', '## Flags (reported, not changed)', '']

    def section(title, items, header, fmt, empty='None.'):
        L.extend(['### %s (%d)' % (title, len(items)), ''])
        if items:
            L.extend([header, '|' + '---|' * header.count('|', 1)])
            L.extend(fmt(x) for x in items)
        else:
            L.append(empty)
        L.append('')

    section('Whitespace stripped', res['stripped'], '| Designator | Field | Raw value |',
            lambda t: '| %s | %s | `%r` |' % (t[0], t[1], t[2]))
    def asbuilt(ref, mpn):
        if base is None:
            return 'no baseline'
        b = base.get(ref)
        if not b:
            return 'designator not in the baseline'
        return 'same MPN' if b['MPN'] == mpn else 'baseline MPN `%s`' % b['MPN']
    section('MPNs with commas, slashes or other unusual characters', h['odd_mpn'],
            '| Designator | MPN | Characters | As-built %s |' % (label or 'baseline'),
            lambda t: '| %s | `%s` | `%s` | %s |' % (t[0], t[1], t[2], asbuilt(t[0], t[1])))
    section('Non-ASCII or control characters', h['non_ascii'], '| Designator | Field | Value |',
            lambda t: '| %s | %s | %s |' % (t[0], t[1], md(t[2])))
    section('Double spaces', h['double_space'], '| Designator | Field | Value |',
            lambda t: '| %s | %s | `%s` |' % (t[0], t[1], t[2]))
    section('Cells starting with = (written as text, not formulas)', h['formula_like'],
            '| Designator | Field | Value |', lambda t: '| %s | %s | `%s` |' % (t[0], t[1], t[2]))
    section('Fitted rows with DNP / DNM inside Value, MPN or Footprint', h['dnp_text'],
            '| Designator | Field | Value |', lambda t: '| %s | %s | %s |' % (t[0], t[1], md(t[2])))
    if h['dnp_text']:
        L.extend(['MacroFab\'s 2016 BOM rule turns population off when Value or MPN contains DNP / DNM (substring or '
                  'exact match: unverified). Check these stay populated after import.', ''])
    section('MacroFab house parts (MF-), kept as in the schematic', h['house'], '| MPN | Manufacturer | Designators |',
            lambda t: '| %s | %s | %s |' % (md(t[0][0]), md(t[0][1]), compress_refs(t[1])))
    section('Fitted rows without a Manufacturer', h['no_manufacturer'], '| Designator | MPN |',
            lambda t: '| %s | %s |' % (t[0], md(t[1])))
    section('Manufacturer from the MANUFACTURER fallback', res['fallback'], '| Designator |', lambda t: '| %s |' % t)
    section('Populate 0 rows without an MPN', [compress_refs(h['pop0_no_mpn'])] if h['pop0_no_mpn'] else [],
            '| Designators |', lambda t: '| %s |' % t)
    section('Manufacturer names', h['mfr_names'], '| Manufacturer | Rows |', lambda t: '| %s | %d |' % (md(t[0]), t[1]))
    section('Manufacturer-name variants (same name once suffixes are dropped, or one contains the other)',
            h['mfr_variants'], '| Spellings |', lambda g: '| %s |' % ', '.join('`%s`' % md(x) for x in g))
    section('Manufacturer names MacroFab spells differently', h['mfr_known'], '| Name | Note |',
            lambda t: '| %s | %s |' % (md(t[0]), md(t[1])))
    section('Same MPN under different Manufacturer names', h['mpn_two_mfrs'], '| MPN | Manufacturers |',
            lambda t: '| %s | %s |' % (md(t[0]), ', '.join('`%s`' % md(x) for x in t[1])))
    section('Value + footprint collisions (same Value and footprint, different MPNs)', h['collisions'],
            '| Value | Footprint | MPN: designators |',
            lambda t: '| %s | %s | %s |' % (
                md(t[0][0]), md(t[0][1]), md('; '.join('%s: %s' % (m or '(none)', compress_refs(v)) for m, v in t[1]))))
    if h['collisions']:
        L.extend(['After the import, check that each of these designators keeps its own MPN (%s).' % LINE_GROUPING,
                  ''])
    section('Value + footprint groups that mix fitted and Populate 0 rows', h['mixed_populate'],
            '| Value | Footprint | Populate 1 | Populate 0 |',
            lambda t: '| %s | %s | %s | %s |' % (md(t[0][0]), md(t[0][1]), compress_refs(t[1]), compress_refs(t[2])))
    if h['mixed_populate']:
        L.extend(['After the import, check every Populate 0 designator above by name: it must stay Do Not Place, and '
                  'the fitted ones must stay fitted (%s).' % LINE_GROUPING, ''])
    return '\n'.join(L).rstrip('\n') + '\n'


# ---------------------------------------------------------------- main

def run(a, work, s=None):
    """One build; a: the parsed arguments, s: the resolved settings (config.resolve). Returns the exit code."""
    s = s if s is not None else config.resolve(a, a.repo)
    label = s.baseline_label
    # the row-rule text names the baseline only when one is configured (--no-baseline still names it)
    text_label = label if (getattr(a, 'baseline', None) or s.baseline_paths) else None
    generator = s.generator_prefix + TOOL
    cli = kproject.kicad_cli(s.kicad_cli)
    info = kproject.build(os.path.join(work, 'proj'), a.repo, rev=a.rev, project_dir=s.project_dir, library='no',
                          require_dru=s.require_dru)
    sha = info['sha']
    proj = os.path.dirname(info['board'])
    sch = os.path.join(proj, info['name'] + '.kicad_sch')
    cdate, subject = kproject.git(a.repo, 'log', '-1', '--format=%cI%n%s', sha).split('\n', 1)
    when = kproject.iso_datetime(cdate).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    revision = project_revision(proj, info['name'], info['board'])
    name = a.name or config.format_name(s.name_template, info['name'], revision)
    if not name:
        raise Fail('no REVISION text variable in the project: pass --name')
    version = kicad_version(cli)
    rev_label = 'commit `%s` (%s, "%s"), project REVISION %s' % (sha, cdate, subject.strip(), revision)
    refs = [l for l in kproject.git(a.repo, 'for-each-ref', '--contains', sha, '--format=%(refname)',
                                    check=False).splitlines() if l.strip()]

    rows_csv = os.path.join(work, 'rows.csv')
    cmd_rows = bom_check.export(cli, sch, rows_csv, ROWS_EXPORT)
    net = os.path.join(work, 'netlist.xml')
    cmd_net = [cli, 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', net, sch]
    r = subprocess.run(cmd_net, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 or not os.path.exists(net):
        raise Fail('netlist export failed:\n%s\n%s' % (r.stdout, r.stderr))
    os.makedirs(a.out, exist_ok=True)
    out = {k: os.path.join(a.out, name + suffix) for k, suffix in (
        ('xlsx', '_macrofab.xlsx'), ('grouped', '_bom.csv'), ('perref', '_bom_perref.csv'),
        ('diff', '_vs_%s.md' % label), ('checks', '_bom_checks.md'))}
    cmd_g = bom_check.export(cli, sch, out['grouped'], bom_check.GROUPED)
    cmd_p = bom_check.export(cli, sch, out['perref'], bom_check.PERREF)

    comps, net_dups = netlist_comps(net)
    rows, res = build_rows(read_csv(rows_csv), comps, net_dups, board_footprints(info['board']),
                           baseline_label=text_label, non_part_refs=config.compile_refs(s.non_part_refs),
                           non_part_libs=tuple(s.non_part_libs))
    h = hygiene(rows)

    pop1 = [x for x in rows if x['Populate'] == 1]
    pop0 = {x['Designator'] for x in rows if x['Populate'] == 0}
    expect_lines = []
    if a.expect_fitted is not None:
        ok = len(pop1) == a.expect_fitted
        expect_lines.append('%s: Populate 1 rows %d, expected %d' % ('PASS' if ok else 'FAIL', len(pop1),
                                                                   a.expect_fitted))
    if a.expect_unfitted is not None:
        want = expand_refs(a.expect_unfitted)
        ok = want == pop0
        expect_lines.append('%s: Populate 0 set %s expected (%d)%s' % (
            'PASS' if ok else 'FAIL', '==' if ok else '!=', len(want), '' if ok else
            '; extra: %s; missing: %s' % (compress_refs(pop0 - want) or '-', compress_refs(want - pop0) or '-')))

    write_xlsx(out['xlsx'], rows, when, '%s MacroFab BOM' % name, 'make_macrofab_xlsx.py from %s' % sha)

    diff_info = None
    base = None
    if not a.no_baseline:
        spec, base, alts, base_dups = load_baseline(a.baseline, a.repo, sha, info['project_dir'], s.baseline_paths)
        if base is None:
            if spec is not None:
                res['errors'].append(spec)
        else:
            new_label = config.format_name(s.revision_label, info['name'], revision) or name
            text, diff_info = diff_md(name, rev_label, rows, spec, base, alts, base_dups, label=label,
                                      new_label=new_label, generator=generator)
            with open(out['diff'], 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)

    def fmt(cmd, outname, comment=''):
        args = ['kicad-cli']
        for i, x in enumerate(cmd[1:], 1):
            args.append('<sch>' if x == sch else outname if cmd[i - 1] == '-o' else shell_quote(x))
        return ' '.join(args) + ('  # ' + comment if comment else '')
    cmds = [fmt(cmd_g, os.path.basename(out['grouped']), 'grouped BOM (as kicad-bom-check)'),
            fmt(cmd_p, os.path.basename(out['perref']), 'per reference (as kicad-bom-check --perref)'),
            fmt(cmd_rows, 'rows.csv', 'the Populate 1 rows of the xlsx'),
            fmt(cmd_net, 'netlist.xml', 'every symbol with its DNP / BOM / board flags: the Populate 0 rows')]
    with open(out['checks'], 'w', encoding='utf-8', newline='\n') as f:
        f.write(checks_md(name, rev_label, version, cmds, rows, res, h, expect_lines, base=base, refs=refs,
                          label=text_label, generator=generator))

    # summary
    side = res['side']
    print('rev %s = %s (%s), kicad-cli %s, NAME %s' % (a.rev, sha[:9], subject.strip(), version, name))
    print('commit on: %s' % (', '.join(refs[:6]) if refs else 'NO branch or tag'))
    if not refs:
        print('WARNING: %s is on no branch or tag (a scratch commit): its hash is in the xlsx properties and the '
              'reports; re-run on the final commit before committing these files' % sha[:9])
    print('rows %d: Populate 1 = %d (F %d / B %d), Populate 0 = %d: %s'
          % (len(rows), len(pop1), side[(1, 'F.Cu')], side[(1, 'B.Cu')], len(pop0), compress_refs(pop0)))
    print('no row: %s; board-only footprints: %d' % (compress_refs(x[0] for x in res['omitted']) or '-',
                                                      len(res['board_only'])))
    print('flags: odd MPNs %s; MF- house parts %d MPNs; DNP text on fitted rows %s; manufacturer variants %s; '
          'value+footprint collisions %d; mixed-Populate groups %d; whitespace stripped %d'
          % ([x[0] + ' ' + x[1] for x in h['odd_mpn']] or '-', len(h['house']),
             sorted({x[0] for x in h['dnp_text']}) or '-', h['mfr_variants'] or '-', len(h['collisions']),
             len(h['mixed_populate']), len(res['stripped'])))
    if diff_info:
        c = diff_info['counts']
        print('vs %s: added %d, removed %d, changed %d (MPN %d, Manufacturer %d, Populate %d)'
              % (label, len(diff_info['added']), len(diff_info['removed']), diff_info['changed'], c['MPN'],
                 c['Manufacturer'], c['Populate']))
    for x in expect_lines:
        print(x)
    for e in res['errors']:
        print('ERROR:', e)
    print('wrote:', ', '.join(os.path.basename(p) for k, p in out.items() if os.path.exists(p)), '->',
          config.show_path(a.out))
    failed = res['errors'] or any(x.startswith('FAIL') for x in expect_lines)
    print('CHECKS FAILED' if failed else 'CHECKS PASSED')
    return 1 if failed else 0


CONFIG_KEYS = ('project_dir', 'name_template', 'baseline_label', 'revision_label', 'non_part_refs', 'non_part_libs',
               'generator_prefix', 'require_dru', 'kicad_cli')


def build_parser():
    ap = argparse.ArgumentParser(prog='kicad-macrofab-bom', description=config.cli_description(__doc__),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rev', nargs='?', default='HEAD', metavar='REV', help='the commit (default: HEAD)')
    ap.add_argument('--out', required=True, metavar='DIR', help="output folder, created if needed (the package's "
                                                                'bom/ folder)')
    ap.add_argument('--repo', default='.', metavar='DIR', help='the git repository (default: the current folder)')
    ap.add_argument('--name', help='output name prefix (default: the name template)')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--baseline', metavar='SPEC', help='BOM xlsx to diff against: REV:PATH (read with git show) or a '
                                                      "local file (default: the config file's baseline_paths)")
    g.add_argument('--no-baseline', action='store_true', help='skip the diff against a baseline')
    ap.add_argument('--expect-fitted', type=int, metavar='N', help='fail unless exactly N rows have Populate 1')
    ap.add_argument('--expect-unfitted', metavar='REFS', help='fail unless the Populate 0 designators are exactly '
                                                              'REFS (comma list; ranges like TP1-TP8)')
    ap.add_argument('--work', metavar='DIR', help='keep the project copy and the intermediate exports there (an '
                                                  'empty or new folder); default: a temp folder, removed')
    config.add_args(ap, CONFIG_KEYS)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass
    ap = build_parser()
    a = ap.parse_args(argv)
    if openpyxl is None:
        print("ERROR: openpyxl is required (pip install openpyxl; KiCad's bundled python usually lacks it)")
        return 2
    try:
        s = config.resolve(a, a.repo)
    except config.ConfigError as e:
        print('ERROR:', e)
        return 2
    if re.search(r'[\\/:*?"<>|]', s.baseline_label):
        print('ERROR: baseline label %r is not usable in a file name' % s.baseline_label)
        return 2
    own = None
    if a.work:
        if os.path.exists(a.work) and os.listdir(a.work):
            print('ERROR: --work %s is not empty' % config.show_path(a.work))
            return 2
        os.makedirs(a.work, exist_ok=True)
        work = a.work
    else:
        work = own = tempfile.mkdtemp(prefix='macrofab_xlsx_')
    try:
        rc = run(a, work, s)
    except (kproject.ProjectError, config.ConfigError, Fail, OSError, ValueError, zipfile.BadZipFile) as e:
        print('ERROR:', e)
        rc = 2
    finally:
        if own:
            shutil.rmtree(own, ignore_errors=True)
    return rc


if __name__ == '__main__':
    sys.exit(main())
