# beta-field-windows

> Only the **last run** is kept. Opening a new window **deletes the previous
> run's artifacts first** (logs, captures, pulled instances) — git history and
> the logbook carry what a past round taught, so nothing durable is lost.
> `emit_instances.py` is the only code that persists between runs.

The how-to for running a window — the two window kinds, the box layouts, the
`put_layout.sh` gate, the tunnel, running a round, and the On Tap list — is
`../field-window-recipe.md`. This folder is just the tool and the last run.

## Last run — round three (2026-09-19)

Two 5-minute `--debug` windows on scada `dfc35644` (`jm/spruce-unlimbo`), one
target each, no LTN; both wrote to one broker capture (21 messages).

- **beech** — no deed in the box config dir: one `layout.lite` (85 ShNodes)
  to the LTN and one Warning glitch (`no-ta-deed`), each once.
- **spruce** — closed after ~2.5 min to restore the winter hack: one
  `layout.lite` (98 ShNodes, `ActuationAuthority` Active) and one `ta.deed`,
  each once; a pico-cycler reboot after which four pico-fed actors sent a Debug
  `pico-identity-matches` glitch (no "differs from the layout" Warning); two
  `gridworks.event.problem` (`fancoil-depth3`, `pipes1-depth3`).

Files: `broker-capture-20260919-141154.jsonl`, `beech-window-…141315.log`, the
85-line `spruce-window-…141515.excerpt.log` (cut from the 1.6 MB DEBUG trace),
each with a provenance sidecar; `instances/{beech,spruce}-gw.experiment.run-000.json`.
Capture stamps are the laptop clock, ~72 s ahead of the boxes.

## emit_instances.py

Builds `instances/<house>-gw.experiment.run-000.json` from the first and last
stamped line of each window log, constructing through the gwexp snapshot class
and reading the written file back through the codec. The excerpt keeps the
first and last stamps, so the spruce instance regenerates unchanged:

    uv run python emit_instances.py

Read a committed instance back through the codec:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"
