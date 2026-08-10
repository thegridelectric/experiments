# 2026-06-11 — Migrating a stale layout: an accidental sema teaching story

**Why (unplanned):** the dashboard experiment needed a loadable House0; the
real `oak.generated.json` (Feb) was stale, so migrating it became an EDD
experiment by accident.

**Found — the whole sema argument in one migration, both sides.**

*Where I DID just use the sema (the actual moment):* oak's data channels
lacked the new `data.channel.gt` `Quantity` field. My first instinct was
archaeology — I started hand-building a `TelemetryName→Quantity` map by
scraping current layouts. It broke on the first uncovered name,
`GpmTimes100`. The fix was to stop scraping and **just use the sema**:
"rather than hand-map it, let me use `UNIT_TO_QUANTITY` (the canonical
projection Axiom 2 itself enforces) to get the Quantity" —
`UNIT_TO_QUANTITY[TelemetryName.GpmTimes100]` → `FlowRate`, authoritative,
never misses a name. Same move for device-type ids
(`CACS_BY_MAKE_MODEL[MakeModel]` → canonical UUID) and every stale `Version`
(the type's own literal names the target). The tell: the moment a migration
makes me *scrape* instead of *look up*, the thing I'm scraping for wants a
sema home.

*Where there was no sema (the gotcha, costly, less sure):* the derived-channel
**strategy names** (`linear-fit`→`affine`, `layer-by-layer`→`system-model`)
have no authoritative record of what became what, so I had to **infer** the
rename by diffing current vs stale layouts.

Same task, two worlds: sema-typed = authoritative migration; dangling =
archaeology. `oak`'s deeper derived-channel rework (new required
`EmissionMethod`/`EmitPeriodS`) is a slice of the layout-augments fold, not
a hand-patch — so we stopped grinding and used a current layout instead.

**Artifact kept:** `make_imaginary_layout.py` — the wand that makes a real
layout imaginary (fresh instance UUIDs; canonical device-type UUIDs;
refreshes stale versions; validates by loading). Proven on
`house0-layout.json` → loadable imaginary House0 (103 instance ids
re-randomized, 6 device-type ids canonicalized). The kind of reusable
tool EDD throws off.

## Folder contents & experimental method

The migration ran against June-era layouts and libraries and no
longer reproduces; the files here are the archived record, verbatim
(scripts excluded from the pyright gate):

- `make_imaginary_layout.py` — the wand above.
- `house0.imaginary.json` — its proven output, the loadable imaginary
  House0 the sim experiments consumed.
- `layout_roundtrip_check.py` — the same thread's cross-carrier
  check: every instance in a scada-format layout decoded through the
  sema runtime.
