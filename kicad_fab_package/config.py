"""Settings shared by the tools, and KiCad install detection.

Every setting has a generic built-in default. Precedence, highest first:

  1. the command-line flag
  2. an environment variable (only kicad_cli, kicad_python and kicad_3dmodel_dir have one)
  3. the config file
  4. the built-in default (for the KiCad paths: auto-detection)

Config file (optional, one of):
  --config FILE, else $KICAD_FAB_CONFIG, else kicad-fab.toml or kicad-fab.json at the top level of the git
  repository the tool works on (--repo). TOML needs Python 3.11+ or the `tomli` package; JSON always works.
  Keys are flat (no table). Unknown keys are an error, so a typo does not pass silently.

Keys (see docs/configuration.md):
  project_dir          str   project folder inside the repo (default: auto-detected)
  name_template        str   default output NAME; {project} and {revision} (default '{project}_v{revision}')
  library_dir          str   library folder relative to project_dir: a submodule or a plain folder such as ../lib
                             (default: none)
  library_paths        list  folders of the library copied into the project copy (default: the whole library)
  library_model_paths  list  folders of the library holding 3-D models (default: the whole library)
  generator_prefix     str   prefix of the tool name written into the outputs (default '')
  require_dru          bool  require <project>.kicad_dru in the project copy (default false)
  kicad_cli            path  kicad-cli executable                                  env KICAD_CLI
  kicad_python         path  KiCad's bundled python (imports pcbnew)               env KICAD_PYTHON, KICAD10_PYTHON
  kicad_3dmodel_dir    path  KiCad's 3-D model library                              env KICAD10_3DMODEL_DIR
  ibom_pkg             path  unpacked InteractiveHtmlBom package folder (default: none, the iBOM is skipped)
  bom_csv              str   committed grouped BOM csv, repo-relative (bom_check; default: none)
  baseline_paths       list  baseline BOM xlsx files to diff against, project-relative, first found at REV wins
  baseline_label       str   label of that baseline in report text and file names (default 'baseline')
  revision_label       str   how the BOM diff report calls the new build; {project} and {revision} (default
                             'v{revision}'; NAME when there is no revision)
  non_part_refs        regex designators of fiducials and mounting holes (default '^(FID|H)\\d+$'; '' = none)
  non_part_libs        list  footprint libraries of fiducials and mounting holes (default Fiducial, MountingHole)
  xyrs_non_part_refs   regex non_part_refs for the XYRS only (default: non_part_refs)
  xyrs_non_part_libs   list  non_part_libs for the XYRS only (default: non_part_libs)
  require_filled_vias  bool  a board without filled-and-capped vias fails the filled-via checks (default false)
  pcbway               bool  kicad-fab-export also writes the PCBWay BOM, centroid files and Gerber zip (default false)
  pos_note_keeps      str   what the manifest note says the --exclude-dnp position file still keeps

Relative paths of the four path keys are resolved against the config file's folder. A bool key's flag --x sets it,
--no-x clears it.
"""
import collections
import copy
import json
import os
import re
import shutil
import subprocess
import sys

CONFIG_ENV = 'KICAD_FAB_CONFIG'
CONFIG_NAMES = ('kicad-fab.toml', 'kicad-fab.json')
NON_PART_REFS = r'^(FID|H)\d+$'                 # fiducials and mounting holes, by designator ...
NON_PART_LIBS = ['Fiducial', 'MountingHole']    # ... and by KiCad's footprint libraries for them
POS_NOTE_KEEPS = ('the parts excluded from the BOM but not DNP (test points, for example), fiducials and mounting '
                  'holes')

# key -> (default, kind); kind is 'str', 'path', 'list', 'bool' or 'regex' (a str that must compile)
KEYS = collections.OrderedDict([
    ('project_dir', (None, 'str')),
    ('name_template', ('{project}_v{revision}', 'str')),
    ('library_dir', (None, 'str')),
    ('library_paths', ([], 'list')),
    ('library_model_paths', ([], 'list')),
    ('generator_prefix', ('', 'str')),
    ('require_dru', (False, 'bool')),
    ('kicad_cli', (None, 'path')),
    ('kicad_python', (None, 'path')),
    ('kicad_3dmodel_dir', (None, 'path')),
    ('ibom_pkg', (None, 'path')),
    ('bom_csv', (None, 'str')),
    ('baseline_paths', ([], 'list')),
    ('baseline_label', ('baseline', 'str')),
    ('revision_label', ('v{revision}', 'str')),
    ('non_part_refs', (NON_PART_REFS, 'regex')),
    ('non_part_libs', (NON_PART_LIBS, 'list')),
    ('xyrs_non_part_refs', (None, 'regex')),          # None: the same as non_part_refs
    ('xyrs_non_part_libs', (None, 'list')),           # None: the same as non_part_libs
    ('require_filled_vias', (False, 'bool')),
    ('pcbway', (False, 'bool')),
    ('pos_note_keeps', (POS_NOTE_KEEPS, 'str')),
])
TEMPLATE_KEYS = ('name_template', 'revision_label')
ENV_VARS = {
    'kicad_cli': ('KICAD_CLI',),
    'kicad_python': ('KICAD_PYTHON', 'KICAD10_PYTHON'),
    'kicad_3dmodel_dir': ('KICAD10_3DMODEL_DIR',),
}


class ConfigError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ config file
def repo_top(repo='.'):
    """Top level of the git work tree holding repo, or repo itself when it is not in one."""
    try:
        r = subprocess.run(['git', '-C', repo, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    except OSError:
        return os.path.abspath(repo)
    top = r.stdout.strip()
    return os.path.abspath(top) if r.returncode == 0 and top else os.path.abspath(repo)


def find_config(path=None, repo='.'):
    """The config file to read: path, else $KICAD_FAB_CONFIG, else kicad-fab.toml / .json at the repo top level."""
    for given, what in ((path, '--config'), (os.environ.get(CONFIG_ENV), CONFIG_ENV)):
        if given:
            if not os.path.isfile(given):
                raise ConfigError('%s: config file not found: %s' % (what, show_path(given)))
            return os.path.abspath(given)
    top = repo_top(repo)
    for name in CONFIG_NAMES:
        p = os.path.join(top, name)
        if os.path.isfile(p):
            return p
    return None


def _read_toml(path):
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            raise ConfigError('%s: reading TOML needs Python 3.11+ or the tomli package (pip install tomli), or '
                              'use a JSON config file' % show_path(path))
    with open(path, 'rb') as f:
        return tomllib.load(f)


def check_name_template(template, key='name_template'):
    try:
        template.format(project='p', revision='r')
    except (KeyError, IndexError, ValueError) as e:
        raise ConfigError('%s %r: only {project} and {revision} may be used (%s)' % (key, template, e))
    return template


def check_regex(pattern, key):
    try:
        re.compile(pattern)
    except re.error as e:
        raise ConfigError('%s %r: not a valid regular expression (%s)' % (key, pattern, e))
    return pattern


def compile_refs(pattern):
    """A designator regex setting compiled for re.match, or None for '' / None (no designator matches)."""
    return re.compile(pattern) if pattern else None


def load_config(path):
    """The validated key/value dict of a config file ({} for None)."""
    if path is None:
        return {}
    try:
        if path.lower().endswith('.toml'):
            data = _read_toml(path)
        else:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError('%s: %s' % (show_path(path), e))
    if not isinstance(data, dict):
        raise ConfigError('%s: the top level must be a table / object of keys' % show_path(path))
    unknown = sorted(set(data) - set(KEYS))
    if unknown:
        raise ConfigError('%s: unknown key(s) %s; known: %s' % (show_path(path), ', '.join(unknown), ', '.join(KEYS)))
    out = {}
    base = os.path.dirname(os.path.abspath(path))
    for key, value in data.items():
        kind = KEYS[key][1]
        if value is None:
            continue
        if kind == 'list':
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError('%s: %s must be a list of strings' % (show_path(path), key))
            value = list(value)
        elif kind == 'bool':
            if not isinstance(value, bool):
                raise ConfigError('%s: %s must be true or false' % (show_path(path), key))
        elif not isinstance(value, str):          # 'str', 'path' and 'regex'
            raise ConfigError('%s: %s must be a string' % (show_path(path), key))
        if kind == 'path' and value:
            value = os.path.expanduser(value)
            if not os.path.isabs(value):
                value = os.path.normpath(os.path.join(base, value))
        if key in TEMPLATE_KEYS:
            check_name_template(value, '%s: %s' % (show_path(path), key))
        elif kind == 'regex':
            check_regex(value, '%s: %s' % (show_path(path), key))
        out[key] = value
    return out


# ------------------------------------------------------------------------------------------------ settings
class Settings(dict):
    """The resolved settings; keys are readable as attributes. .config_path names the file read (or None)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def cli_description(doc):
    """A module docstring for argparse's description: without its 'usage:' paragraph, since argparse prints its own
    usage line."""
    return re.sub(r'(?ms)^usage: .*?\n\n', '', doc, count=1)


def show_path(path):
    """A path as the tools print it: with '/' separators on Windows too, as in the docs."""
    return str(path).replace(os.sep, '/') if os.sep != '/' else str(path)


def csv_list(text):
    """argparse type: 'a, b,c' -> ['a', 'b', 'c']; '' -> []."""
    return [p.strip() for p in text.split(',') if p.strip()]


FLAGS = collections.OrderedDict([
    ('project_dir', ('--project-dir', dict(metavar='DIR', help='project folder inside the repo, "." for the top '
                                                               'level (default: auto-detected, the folder of the only '
                                                               '.kicad_pro with a .kicad_pcb of the same name)'))),
    ('name_template', ('--name-template', dict(metavar='TEMPLATE', help='NAME when --name is not given: {project} '
                                                                        '= KiCad project name, {revision} = its '
                                                                        "REVISION (default '{project}_v{revision}')"))),
    ('library_dir', ('--library-dir', dict(metavar='DIR', help='library folder relative to the project folder: a '
                                                               'git submodule or a plain folder of the repository '
                                                               '(e.g. ../lib); its files are added to the project '
                                                               'copy ("" = none; default: none)'))),
    ('library_paths', ('--library-paths', dict(type=csv_list, metavar='P1,P2', help='folders of the library put '
                                                                                    'into the project copy (default: '
                                                                                    'the whole library)'))),
    ('library_model_paths', ('--library-model-paths', dict(type=csv_list, metavar='P1,P2',
                                                           help='folders of the library holding 3-D models (default: '
                                                                'the whole library)'))),
    ('generator_prefix', ('--generator-prefix', dict(metavar='PREFIX', help='prefix of the tool name written into '
                                                                            "the outputs (default '')"))),
    ('require_dru', ('--require-dru', dict(help='require <project>.kicad_dru in the project copy'))),
    ('kicad_cli', ('--kicad-cli', dict(metavar='PATH', help='kicad-cli (env KICAD_CLI; default: the newest standard '
                                                            'install, then PATH; a kicad-cli older than KiCad 10 '
                                                            'gets a warning)'))),
    ('kicad_python', ('--kicad-python', dict(metavar='PATH', help="KiCad's python with pcbnew (env KICAD_PYTHON or "
                                                                  'KICAD10_PYTHON; default: next to kicad-cli, then '
                                                                  'the standard install folders)'))),
    ('kicad_3dmodel_dir', ('--kicad-3dmodel-dir', dict(metavar='DIR', help="KiCad's 3-D model library (env "
                                                                           'KICAD10_3DMODEL_DIR; default: '
                                                                           'auto-detected next to kicad-cli)'))),
    ('ibom_pkg', ('--ibom-pkg', dict(metavar='DIR', help='unpacked InteractiveHtmlBom package folder (run with '
                                                         "KiCad's python); without it the iBOM is skipped"))),
    ('baseline_label', ('--baseline-label', dict(metavar='LABEL', help='label of the baseline BOM in the report '
                                                                       "text and the diff file name (default "
                                                                       "'baseline')"))),
    ('revision_label', ('--revision-label', dict(metavar='TEMPLATE', help='how the diff report calls the new build: '
                                                                          '{project}, {revision} (default '
                                                                          "'v{revision}'; NAME without a revision)"))),
    ('non_part_refs', ('--non-part-refs', dict(metavar='REGEX', help='designators of fiducials and mounting holes, '
                                                                     'matched from the start (default %s; "" = none)'
                                                                     % NON_PART_REFS.replace('%', '%%')))),
    ('non_part_libs', ('--non-part-libs', dict(type=csv_list, metavar='L1,L2',
                                               help='footprint libraries of fiducials and mounting holes (default '
                                                    '%s; "" = none)' % ','.join(NON_PART_LIBS)))),
    ('xyrs_non_part_refs', ('--xyrs-non-part-refs', dict(metavar='REGEX', help='--non-part-refs for the XYRS only '
                                                                               '(default: --non-part-refs)'))),
    ('xyrs_non_part_libs', ('--xyrs-non-part-libs', dict(type=csv_list, metavar='L1,L2',
                                                         help='--non-part-libs for the XYRS only (default: '
                                                              '--non-part-libs)'))),
    ('require_filled_vias', ('--require-filled-vias', dict(help='fail the filled-via checks when the board has no '
                                                                'filled-and-capped vias'))),
    ('pcbway', ('--pcbway', dict(help='also write the PCBWay assembly files: BOM xlsx, top and bottom centroid csvs, '
                                      'and the PCBWay Gerber zip'))),
])
# the --no-x flag of each bool key: it clears the key whatever the config file says
NO_FLAG_HELP = {
    'require_dru': 'do not require <project>.kicad_dru, whatever the config file says',
    'require_filled_vias': 'a board without filled-and-capped vias passes the filled-via checks, whatever the config '
                           'file says',
    'pcbway': 'do not write the PCBWay files, whatever the config file says',
}


def add_args(ap, keys, title='configuration'):
    """Add --config and the flags of keys (each default None = not given) to an argparse parser. A bool key gets
    --x (true) and --no-x (false)."""
    g = ap.add_argument_group(title, 'Each is also a config-file key (docs/configuration.md); a flag '
                                     'wins over the environment, which wins over the config file.')
    g.add_argument('--config', metavar='FILE', help='config file (default: $%s, else %s at the repo top level)'
                                                    % (CONFIG_ENV, ' or '.join(CONFIG_NAMES)))
    for key in keys:
        flag, kw = FLAGS[key]
        if KEYS[key][1] == 'bool':
            g.add_argument(flag, dest=key, action='store_const', const=True, default=None, **kw)
            g.add_argument('--no-' + flag[2:], dest=key, action='store_const', const=False, default=None,
                           help=NO_FLAG_HELP[key])
        else:
            g.add_argument(flag, dest=key, default=None, **kw)
    return g


def resolve(args=None, repo='.', config_path=None, **overrides):
    """Settings from an argparse namespace (attribute per key, None = not given), the environment, the config file
    and the defaults. overrides: values that win over everything (used by library callers)."""
    path = find_config(config_path or getattr(args, 'config', None), repo)
    cfg = load_config(path)
    out = Settings()
    for key, (default, kind) in KEYS.items():
        v = overrides.get(key)
        if v is None and args is not None:
            v = getattr(args, key, None)
        if v is None:
            for env in ENV_VARS.get(key, ()):
                if os.environ.get(env):
                    v = os.environ[env]
                    break
        if v is None:
            v = cfg.get(key)
        if v is None:
            v = copy.deepcopy(default)
        out[key] = v
    if out['library_dir'] is not None:
        out['library_dir'] = out['library_dir'].replace('\\', '/').strip('/') or None
    if out['xyrs_non_part_refs'] is None:
        out['xyrs_non_part_refs'] = out['non_part_refs']
    if out['xyrs_non_part_libs'] is None:
        out['xyrs_non_part_libs'] = list(out['non_part_libs'])
    for key in TEMPLATE_KEYS:
        check_name_template(out[key], key)
    for key, (_, kind) in KEYS.items():
        if kind == 'regex':
            check_regex(out[key], key)
    out.config_path = path
    return out


def format_name(template, project, revision):
    """The output NAME from the template, or None when the template needs a revision and there is none."""
    if '{revision}' in template and not revision:
        return None
    return template.format(project=project, revision=revision or '')


# ------------------------------------------------------------------------------------------------ KiCad detection
MAC_APP = '/Applications/KiCad/KiCad.app'


def _fwd(p):
    """Forward slashes on Windows (KiCad and every tool here accept them; the paths match KiCad's own docs)."""
    return p.replace('\\', '/') if os.name == 'nt' else p


def _version_key(name):
    return tuple(int(x) for x in re.findall(r'\d+', name))


def windows_kicad_bins():
    """<root>/KiCad/<version>/bin folders, newest version first, for the Program Files roots and the per-user
    install root (%LOCALAPPDATA%/Programs)."""
    roots = []
    for var in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
        v = os.environ.get(var)
        if v and _fwd(v).rstrip('/') not in roots:
            roots.append(_fwd(v).rstrip('/'))
    if not roots:
        roots.append((os.environ.get('SystemDrive') or 'C:') + '/Program Files')
    if os.environ.get('LOCALAPPDATA'):
        roots.append(_fwd(os.environ['LOCALAPPDATA']).rstrip('/') + '/Programs')
    bins = []
    for root in roots:
        base = root + '/KiCad'
        try:
            versions = os.listdir(base)
        except OSError:
            continue
        for v in sorted(versions, key=_version_key, reverse=True):
            bins.append('%s/%s/bin' % (base, v))
    return bins


def kicad_cli_candidates():
    if os.name == 'nt':
        return [b + '/kicad-cli.exe' for b in windows_kicad_bins()]
    if sys.platform == 'darwin':
        return [MAC_APP + '/Contents/MacOS/kicad-cli']
    return ['/usr/bin/kicad-cli', '/usr/local/bin/kicad-cli']


def find_kicad_cli(explicit=None):
    """explicit, else KICAD_CLI, else the newest standard install, else kicad-cli on PATH; None if none exists.

    The standard installs come first because PATH often still holds an older KiCad (for example a 9.0 install whose
    bin folder was added by hand); kproject.kicad_cli() warns when the kicad-cli it gets is older than KiCad 10."""
    if explicit:
        return explicit
    if os.environ.get('KICAD_CLI'):
        return os.environ['KICAD_CLI']
    found = next((c for c in kicad_cli_candidates() if os.path.isfile(c)), None)
    return found or shutil.which('kicad-cli')


MIN_KICAD_MAJOR = 10
_version_cache = {}
_warned = set()


def kicad_cli_version(cli):
    """The version text `cli version` prints (e.g. '10.0.7') and its major number, as (text, major); (None, None)
    when it cannot be run or does not print a version."""
    if cli not in _version_cache:
        text = None
        try:
            r = subprocess.run([cli, 'version'], capture_output=True, text=True, encoding='utf-8', errors='replace',
                               timeout=60, stdin=subprocess.DEVNULL)
            m = re.search(r'\b(\d+)\.(\d+)(?:\.\d+)?\S*', r.stdout)
            text = m.group(0) if m else None
        except (OSError, subprocess.SubprocessError):
            pass
        _version_cache[cli] = (text, int(text.split('.')[0]) if text else None)
    return _version_cache[cli]


def warn_if_old_kicad(cli, stream=None):
    """Print one warning to stderr (once per kicad-cli path) when cli is older than KiCad 10. Returns the major
    version (None when unknown: no warning)."""
    text, major = kicad_cli_version(cli)
    if major is not None and major < MIN_KICAD_MAJOR and cli not in _warned:
        _warned.add(cli)
        print('WARNING: %s is KiCad %s; these tools are written for KiCad %d (board format, kicad-cli options). Point '
              '--kicad-cli or KICAD_CLI at a KiCad %d kicad-cli.' % (cli, text, MIN_KICAD_MAJOR, MIN_KICAD_MAJOR),
              file=stream or sys.stderr)
    return major


def kicad_python_candidates(cli=None):
    out = []
    if cli:
        d = _fwd(os.path.dirname(os.path.abspath(cli)))
        if os.name == 'nt':
            out.append(d + '/python.exe')
        elif sys.platform == 'darwin':
            out.append(os.path.normpath(os.path.join(d, '..', 'Frameworks', 'Python.framework', 'Versions',
                                                     'Current', 'bin', 'python3')))
        else:
            out.append(os.path.join(d, 'python3'))
    if os.name == 'nt':
        out += [b + '/python.exe' for b in windows_kicad_bins()]
    elif sys.platform == 'darwin':
        out.append(MAC_APP + '/Contents/Frameworks/Python.framework/Versions/Current/bin/python3')
    else:
        out.append('/usr/bin/python3')
    return out


def find_kicad_python(explicit=None, cli=None):
    """explicit, else KICAD_PYTHON / KICAD10_PYTHON, else the python next to kicad-cli or in a standard install;
    None if none exists."""
    if explicit:
        return explicit
    for env in ENV_VARS['kicad_python']:
        if os.environ.get(env):
            return os.environ[env]
    return next((c for c in kicad_python_candidates(cli) if os.path.isfile(c)), None)


def kicad_3dmodel_candidates(cli=None):
    out = []
    if cli:
        d = os.path.dirname(os.path.abspath(cli))
        if sys.platform == 'darwin':
            out.append(_fwd(os.path.normpath(os.path.join(d, '..', 'SharedSupport', '3dmodels'))))
        else:
            out.append(_fwd(os.path.normpath(os.path.join(d, '..', 'share', 'kicad', '3dmodels'))))
    if os.name == 'nt':
        out += [b[:-len('/bin')] + '/share/kicad/3dmodels' for b in windows_kicad_bins()]
    elif sys.platform == 'darwin':
        out.append(MAC_APP + '/Contents/SharedSupport/3dmodels')
    else:
        out += ['/usr/share/kicad/3dmodels', '/usr/local/share/kicad/3dmodels']
    return out


def find_kicad_3dmodel_dir(explicit=None, cli=None):
    """explicit, else KICAD10_3DMODEL_DIR, else KiCad's model library next to kicad-cli or in a standard install;
    None if none exists (KiCad's own default then applies)."""
    if explicit:
        return explicit
    if os.environ.get('KICAD10_3DMODEL_DIR'):
        return os.environ['KICAD10_3DMODEL_DIR']
    return next((c for c in kicad_3dmodel_candidates(cli) if os.path.isdir(c)), None)
