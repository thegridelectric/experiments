# beta-field-windows

> Every run is kept: one folder per window under `runs/`, indexed in
> `runs.md`. The folder top holds the tools (`emit_instances.py`,
> `emit_readings.py`) and the index. The recipe's "Records" section says
> what a run folder holds.

The how-to for running a window — the two window kinds, the box layouts, the
`put_layout.sh` gate, the tunnel, running a round, and the On Tap list — is
`../field-window-recipe.md`. This folder is the tools, the index and the runs.

## Round five (2026-09-27, maple), the last run filed at the folder top

One 11-minute window at maple on scada `92b4e5d1` (`jm/spruce-unlimbo`),
`--debug`, no LTN, sieg loop strategy `HoldFullSend`, `ActuationAuthority`
Active, heat pump off (56 W). The window verifies basic-sieg change 4d
(the send-line pico posts as `sieg-send`; `sieg-send-flow` is an identity
over it and `primary-flow` the sum with `sieg-flow`) and re-checks 4ci
(every direct boss commands its relays at boot). The full read is
`maple-4d-window-analysis.md`.

- **4d verifies.** `sieg-send-flow` and `primary-flow` report through the
  whole window; once flow was nonzero the `sieg-send-flow` age on the
  strip stayed between 1 s and 20 s. On all 22 strip lines with values,
  and on all 449 `primary-flow` readings in the two `report.event`s,
  `primary-flow` = `sieg-flow` + `sieg-send-flow` within 0.01 gpm;
  `sieg-send-flow` matches `sieg-send` exactly in values and stamps.
- **The move to send.** `StartKeepingLess` at 18:32:56.096 to
  `ResetToFullySend` at 18:34:46.368 (box clock), a travel of 110 s;
  during it `sieg-flow` fell 4.85 → 0.00 gpm and `sieg-send` rose
  0.00 → 4.13 gpm.
- **4ci holds.** hp-boss, local control, sieg-loop and pico-cycler all
  commanded their relays within 3.4 s of boot; every command acked; no
  `relay_silent`, no `relay_nack`.
- **Glitches: seven, all at boot, all known kinds.** Six `params-version`
  Warnings: the four tank picos post `tank.module.params` 110 (scada
  takes 200) and the two BTU picos post `async.btu.params` 000 (scada
  takes 100, logged as "malformed BtuMeter parameters"); readings still
  flowed from all six. One `disabled-roster` Warning for
  `primary-pump-pwr`. None after 18:33:16.
- **Ages and gaps.** `sieg-flow` reached 277 s while at 0 in FullySend
  (the sieg-btu includes a zero every ~300 s); power and analog-temp
  channels reach 300 s and never pass it; `dist-flow` had a boot
  `PicoMissing` and then posts only when flow changes. Two things with no
  cause in the log: `transactive-power` never had a value and is absent
  from both reports; the zone heat-call periodic emission ran 176 s late
  (`now=1790548676.2 next=1790548500`), which reads as the emission
  firing only when a power-meter reading arrives.
- **scada2** booted and linked; one 10 ms ack timeout at 18:33:00.964 on
  its boot ping, before the primary had subscribed.
- **Reports stayed on the box** (no LTN): 16 events, 2 `report.event`
  (the boot partial and the 22:35-22:40Z slot). The report lists are in
  arrival order, not time order.

Files: `broker-capture-20260927-183402.jsonl` (35 messages),
`maple-window-…184556.log.gz`, `maple2-window-…184606.log`, `maple-events/`,
`maple-4d-window-analysis.md`, each with a provenance sidecar;
`instances/maple-gw.experiment.run-000.json`. Capture stamps are the laptop
clock, ~70 s ahead of the box.

## emit_instances.py

Builds `instances/<house>-gw.experiment.run-000.json` from the first and last
stamped line of each window log, constructing through the gwexp snapshot class
and reading the written file back through the codec. Regenerate the two instances from the logs in this folder:

    uv run python emit_instances.py

Read a committed instance back through the codec:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"
