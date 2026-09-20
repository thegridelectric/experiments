# spruce-pico-params, 2026-09-19

> What this is: why some spruce picos come back from a power cycle and
> deliver readings without ever posting their params word. Verdict: the
> boot-time params post is made once and sometimes not at all, different
> picos on different boots; nothing is wrong with the path, the name or the
> word. The likely mechanism, read from the firmware and not observed
> directly, is a WiFi link that comes up after the 10 s connect timeout.
> The logbook entry is the index record.

## Why

A pico posts its params word to the scada once, at its own boot, and the
scada checks the pico's board and MicroPython version against the layout
only inside that post. In the 2026-09-19 beta field window four spruce
picos (fancoil, pipes1, primary-btu, dist-btu) rebooted, delivered
readings, and posted no params, so their identity was never checked and
they ran on whatever capture settings they booted with. The scada log
could not say which of three things happened: the pico never sent the
post, the scada dropped it for a name mismatch (no log line), or it went
to a path nothing serves (web access logging is off). Tracked as OPS-552;
the firmware fix is OPS-553.

## Setup

Spruce box, heating season, zones 1 and 2 calling.

- **Stopped for each cycle:** `gwspaceheat` and `gwspaceheat-restart.timer`.
  `spruce-winter-hack` (the plant controller) was left running, after
  confirming from its source that it uses neither BCM 23 nor port 8000.
- **In the scada's place:** the starter-scripts API listener
  (`uvicorn rest_api:app`, port 8000, cwd `/tmp/pico-params` so it wrote
  nothing in the home dir), which logs every request and prints the params
  it receives.
- **The rail:** the 5 V pico rail was cut by driving the gw108 Vdc relay
  pin (BCM 23) HIGH from an inline `python3 -c`, then LOW again; the relay
  is wired normally closed, so LOW powers the picos.

As run, on the box (cycle 2; cycle 1 had no timestamper, an 8 s cut and a
120 s watch):

    sudo systemctl stop gwspaceheat gwspaceheat-restart.timer
    mkdir -p /tmp/pico-params && cd /tmp/pico-params
    PYTHONPATH=/home/pi/starter-scripts uvicorn rest_api:app --host 0.0.0.0 --port 8000 2>&1 \
      | while IFS= read -r l; do echo "$(date +%H:%M:%S) $l"; done > cycle2-api.log &
    sleep 25
    python3 -c "import RPi.GPIO as G,time; G.setmode(G.BCM); G.setwarnings(False); G.setup(23,G.OUT); G.output(23,G.HIGH); time.sleep(10); G.output(23,G.LOW)"
    sleep 150; pkill -f 'uvicorn rest_api'
    sudo systemctl start gwspaceheat gwspaceheat-restart.timer
    rm -rf /tmp/pico-params        # after copying the logs off

The command lines are reconstructed from `timeline.txt`; the run was typed
inline and left no script.

## Found

**The params post is sent correctly when it is sent, and whether it is
sent varies from boot to boot.** Across two power cycles every params
request went to the expected path, carried the layout's `ActorNodeName`
and `HwUid`, and got a 200; there was no 404 and no unknown path in either
run.

| pico | cycle 1 (rail on 17:36:07) | cycle 2 (rail on 17:40:28) |
|---|---|---|
| buffer | params | params |
| tank1 | readings only | readings only |
| fancoil | params | readings only |
| pipes1 | readings only | params |
| primary-btu | params | params |
| secondary-btu | readings only | params |
| store-btu | readings only | readings only |
| dist-btu | readings only | params |
| floor1 | nothing (dead) | nothing (dead) |

Three of eight live picos posted params in cycle 1 and five of eight in
cycle 2, and the set differs: fancoil posted in cycle 1 and not cycle 2,
pipes1 the reverse. In the beta window earlier the same day the four that
posted were store-btu, buffer, tank1 and secondary-btu, two of which
posted in neither cycle here. So the four "silent" picos are not a class:
any pico can miss.

Each pico that posted params also posted its `code-update` check just
before it, and each that skipped params skipped `code-update` too (three
and three in cycle 1, five and five in cycle 2). The picos that skipped
were also the slowest to reappear: in cycle 2 the five that posted first
appeared 6 to 13 s after the rail came on, the three that skipped at 15 to
16 s.

The picos run `gridworks-pico` branch `td/pico-easy-fixes`; every params
post was `tank.module.params` `200` or `async.btu.params` `100`, which only
that branch sends. There, both calls sit together at the top of `start()`,
ahead of the reading loop; the first connect gives up after 10 s and
`start()` carries on; and both calls return silently on anything but a
200 (`tank_module/tank_module_3_main_no_net.py:484`). On `main` the connect
waits for the link with no timeout, so the skip cannot happen there. A
link that comes up after the timeout fits the timing above. It was not
observed directly: no pico serial output was captured.

Verdict: PASS (question answered). Not established: that the scada itself
accepts these bodies. The listener takes any `/{node}/…` path without a
layout check, so its 200 is not the scada's.

## Timeline

Box clock, ET.

- 17:35:24 units recorded (all three active); `gwspaceheat` + timer stopped.
- 17:35:39 listener on :8000. 17:35:59 rail off, 17:36:07 rail on (8 s).
- 17:38:07 watch ends; 17:38:10 units started, all three active. 2 min 46 s down.
- 17:39:41 second stop. 17:39:53 listener up. 17:40:18 rail off, 17:40:28
  rail on (10 s); no request arrived while the rail was off.
- 17:42:58 watch ends; 17:43:02 units started; 17:43:05 `gwspaceheat`
  active, timer active, `spruce-winter-hack` active on the same MainPID as
  before the run. BCM 23 left LOW. `/tmp/pico-params` removed.

## Analysis notes

- Cycle 1's listener log is unstamped apart from the listener's own
  bracketed stamps; use `timeline.txt` for the rail times. Cycle 2's lines
  all carry the box clock.
- "Readings only" means no params and no `code-update` request from that
  pico in the watch (120 s in cycle 1, 150 s in cycle 2).
- `timeline.txt` logs "START tcpdump" in cycle 1. `tcpdump` is not
  installed on the box, so that start failed and no request bodies were
  captured on the wire; the listener's printout is the only record of
  them.
- A pico that misses the boot post runs unchecked and with its own
  capture settings until its next boot.

## Folder contents & experimental method

All data here was GENERATED by this experiment; none of it is in the
journal DB or the eventstore, and a re-run produces a new dataset. The run
touched the running system: `gwspaceheat` and its restart timer were
stopped twice (6 min 7 s in total) and the pico rail was cut twice. The
plant controller was not touched.

- `cycle1-api.log`, `cycle2-api.log`: the listener's stdout for each
  cycle. EXTERNAL EVIDENCE, provenance sidecar beside each.
- `timeline.txt`: the run's step log. EXTERNAL EVIDENCE.
- `winter-hack-journal.txt`: `spruce-winter-hack` journal lines up to
  17:39:30, through cycle 1 and to the start of cycle 2. That it ran
  through cycle 2 as well rests on `timeline.txt`: the same MainPID
  (20182) before and after. EXTERNAL EVIDENCE.
- `instances/spruce-gw.experiment.run-000.json`: the run, emitted by
  `emit_instances.py` through the gwexp snapshot class and read back
  through the codec.
- Not yet instances: the eight params bodies the listener printed. Both
  words are registered (`tank.module.params` 200, `async.btu.params` 100);
  they become instances once the two words are in the gwexp snapshot
  seed.

Re-run from scratch: the block under Setup, on the spruce box, in a
bounded window. A re-run is a new dataset.

Regenerate the instance:

    cd ~/GridWorks/experiments/2026-09-19-spruce-pico-params
    uv run python emit_instances.py

Which picos posted params in a cycle, from the evidence:

    grep -E 'POST /[a-z0-9-]+/(tank-module-params|async-btu-params)' cycle2-api.log

No display CSV applies: the folder holds no readings instance.
