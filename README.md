# gridworks-experiments

Real-condition experiments on the GridWorks fleet: the harnesses that
ran, the data they captured, the findings, and machine-readable results
as validated Sema instances.

## Layout

- `logbook.md` — chronological index, one line per experiment, newest
  first. The canonical record of each experiment is the README in its
  folder.
- `<date>-<slug>/` — one folder per experiment: README (why, setup,
  found, data manifest), harness code, captured data, and `instances/`
  holding sema-typed results named `<type-name>.json`.
- `src/gwexp/sema/` — the vendored Sema snapshot runtime (GENERATED —
  never hand-edit). Experiment scripts construct result instances
  through its classes so schema and axioms validate at construction.
  Regenerate with `./regen_sema_snapshot.sh` (expects a sibling `sema`
  checkout; the seed is `src/gwexp/sema_seed_request.yaml`).
- `display.py` — interim wire-encoding → human-readable conversion for
  CSVs (temperatures to °F floats, flows to gpm). Goes away when unit
  harmonization ships.

## Conventions

- Harnesses read fleet facts (board constants, channel declarations)
  from the box's own sema-typed records, never from constants in the
  script; results record provenance including the sha256 + mtime of
  every canonical artifact consumed, and the folder archives the exact
  bytes used.
- Wire-encoded data files are the evidence and stay untouched;
  human-readable `-readable.csv` siblings are regenerated, not edited.
- One instrument master at a time: any bench tool reading a chip the
  deployed service also reads must stop that service — and its restart
  watchdog — for the window.
