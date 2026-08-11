# gridworks-experiments

Real-condition experiments on the GridWorks fleet: the harnesses that
ran, the data they captured, the findings, and machine-readable results
as validated Sema instances.

## Layout

- `logbook.md` — chronological index, one line per experiment, newest
  first. The canonical record of each experiment is the README in its
  folder.
- `<date>-<slug>/` — one folder per experiment: README (start from
  `experiment-README-template.md`; header is "<slug>, <date>", ends
  with a "Folder contents & experimental method" section that opens
  by stating how the data was obtained and what is in the immutable
  store), harness code, captured data, and `instances/` holding
  sema-typed results. The date is the FIRST RUN.
- `future/<slug>/` — queued experiments that have not yet run: README
  (why / setup / protocol, Found open) and any prepared harness code,
  no data. On first run the folder moves to `<run-date>-<slug>/`. Instance filenames are dash-separated
  fields, each field internally LeftRightDot (dashes inside a field
  become dots), ordered `<subject>-<condition?>-<type.name>-<version>.json`
  — the same grammar as the S3 eventstore keys, parsed by a bare
  split on dash.
- `src/gwexp/sema/` — the vendored Sema snapshot runtime (GENERATED —
  never hand-edit). Experiment scripts construct result instances
  through its classes so schema and axioms validate at construction.
  Regenerate with `./regen_sema_snapshot.sh` (expects a sibling `sema`
  checkout; the seed is `src/gwexp/sema_seed_request.yaml`).
- `display.py` — interim wire-encoding → human-readable conversion for
  CSVs (temperatures to °F floats, flows to gpm). Goes away when unit
  harmonization ships.
- `.env` (gitignored, never committed) — `GJK_DB_URL`, the journal-DB
  connection string `pull_readings.py` and the per-experiment analysis
  scripts read. This is the one place journal-DB credentials live on a
  laptop.

## Conventions

- Harnesses read fleet facts (board constants, channel declarations)
  from the box's own sema-typed records, never from constants in the
  script; results record provenance including the sha256 + mtime of
  every canonical artifact consumed, and the folder archives the exact
  bytes used.
- Wire-encoded data files are the evidence and stay untouched;
  human-readable `-readable.csv` / `-display.csv` siblings are
  regenerated, not edited. Every folder holding a `gw.readings`
  instance ends its README with the standard "From the instance to
  the display CSV" paragraph
  (`pull_readings.py --display-from <instance>.json` regenerates the
  CSV with no database or S3 access).
- One instrument master at a time: any bench tool reading a chip the
  deployed service also reads must stop that service — and its restart
  watchdog — for the window.
