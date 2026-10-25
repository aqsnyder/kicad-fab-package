# Contributing

Bug reports, fixes and new checks are welcome. Please open an issue first for anything larger than a fix, so we can
agree on the approach.

## Development setup

```bash
git clone https://github.com/aqsnyder/kicad-fab-package
cd kicad-fab-package
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[test,pdf,toml]"
```

KiCad 10 is needed only for the integration test and for trying the commands on a real project.

## Tests

```bash
python -m pytest -rs
```

- The unit tests use synthetic fixtures only and need no KiCad (they do need `git` on `PATH`).
- `tests/test_integration_kicad.py` commits KiCad's bundled `pic_programmer` demo (or the project folder named by
  `KFP_TEST_KICAD_PROJECT`) into a scratch repository and runs the whole flow. It skips itself, with the reason, when
  KiCad 10 is not found; set `KFP_SKIP_INTEGRATION=1` to skip it on purpose.
- To make sure nothing is auto-detected (as on CI, which has no KiCad), point the KiCad paths at a file that does not
  exist: a path given in `KICAD_CLI` / `KICAD_PYTHON` is used as it is, so detection never runs:

  ```bash
  KICAD_CLI=/nonexistent/kicad-cli KICAD_PYTHON=/nonexistent/python python -m pytest -rs
  ```

CI (`.github/workflows/tests.yml`) runs the suite on Ubuntu and Windows with Python 3.9 and 3.12.

## Style

- Python 3.9 compatible, standard library only in the package except `openpyxl` (and the optional extras); KiCad's
  own Python runs one function of `export_fab.py` as a plain script, so that part must stay importable without the
  package.
- Keep lines to about 120 characters and follow the surrounding code.
- Messages say what is wrong and what to do about it, in plain words. A new check gets a name that reads as the
  expectation (`drill: no slots / routed holes`), a level (`error` fails the run, `warn` is printed), and a row in
  `docs/export-fab.md`.
- Outputs stay reproducible: no timestamps, local paths or random ordering in anything the tools write (use the
  commit date, and the manifest's path tags).
- Keep text files LF (`.gitattributes` enforces it).

## Pull requests

- One topic per pull request, with a test for every behaviour change.
- Update the docs (`README.md`, `docs/`) and `CHANGELOG.md` (under *Unreleased*) in the same pull request.
- Make sure `python -m pytest` passes without KiCad; if you have KiCad 10, run it once with KiCad too.
