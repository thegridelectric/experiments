# hello-rabbit-ltn-trace, 2026-11-03

> What this is: the first trace of a dev scada (gwproactor, MQTT) talking
> to the gwbase LTN (AMQP) across the dev broker, with the LTN taken away
> and brought back, so the design for OPS-659 knows what each side says
> when the link comes up, holds, and goes. Verdict: the link activates
> and holds; the loss is persisted by the scada and said by nobody.

## Why

The gwbase LTN's seam test proves the LTN's half of the scada's link with
a paho stand-in. The scada's half (its link state machine, its reupload,
its 60 s ping and 5 s ack timer) can only be seen with the real scada on
the other side. The design asks the LTN to track the state of its link
and both actors to publish when the link goes away; this run shows what
happens today, before either change.

## Setup

Laptop, `d1` universe, `gw-dev-rabbit` (AMQP 5672, MQTT 1885, vhost
`d1__1`). `gridworks-scada` on `main` (`gws run --message-summary`,
`SCADA_GRIDWORKS_MQTT__PORT=1885`), `gridworks-ltn` on `jm/hello-world`
(`uv run gwltn rabbit`), both on the laptop's placed Nolan pair
(`~/.config/gridworks/{scada,ltn}/`, refreshed from the scada repo's
fixtures first: see the runbook). The LTN's dev identity is
`g.node.gt.json` in this folder (alias
`d1.isone.me.versant.keene.spruce`, the Nolan pair's LTN). The broker
firehose capture (`../capture_broker.py`) ran for the whole window. The
legs ran as one scripted timeline, `run_legs.sh`, under `caffeinate -dims`.
Nothing deployed was touched.

## Found

- **Activation.** The scada's upstream link goes Active on the first
  message from the LTN, which is the LTN's ack of the scada's first
  ack-required ping (22:35:06.916 ping, .918 ack, .926 `awaiting_peer --
  message_from_peer --> active`). The scada then sends
  `gridworks.event.comm.peer.active` and `layout.lite`; the LTN asks
  `send.layout` 1.4 s later and gets a second `layout.lite`.
- **Reupload.** On activation the scada reuploaded about 750 persisted
  events from earlier laptop runs; every one was acked inside 10 ms.
- **Holding.** The LTN pings every 60 s with no ack asked; the scada's
  minutely `report.event` asks for an ack and gets it inside 5 ms. The
  scada did not ping the LTN while the LTN's traffic kept arriving.
- **The LTN leaves (run 3, 00:04:03).** The LTN says nothing as it
  exits. The scada's next `report.event` (00:05:00.020) gets no ack;
  5 s later (00:05:05.019) the link falls `active -- response_timeout
  --> awaiting_peer`, the scada sends ONE ack-required `gridworks.ping`
  to the LTN topic, and nothing else reaches the broker about the loss:
  the `gridworks.event.comm.response.timeout` it generates goes to the
  persister because the upstream link is no longer Active.
- **The LTN returns (00:05:43).** Its `send.layout` (00:05:49.448) is the
  first message the scada hears; the link goes Active again
  (00:05:49.449), and the reupload carries the unacked `report.event`,
  the `response.timeout` event (created 00:05:05) and the new
  `peer.active` event, all acked inside 5 ms, then two `layout.lite`.
- **The LTN has no link state.** It acks and pings, asks for no acks,
  and does not notice the scada leaving. Nothing is published by either
  side at the moment of loss. Bars met: link Active, `layout.lite` on
  activation, a 60 s ping cycle survived, the away-and-back legs
  witnessed. Not tested: a broker drop.
- **Side findings.** The laptop's placed Nolan pair lagged the scada
  fixtures (`NolanLayout` gained required fields) and both actors refused
  to boot on it; `put_layout.sh dev <change>` reads its params prompt
  from its own here-string, not the terminal, so it refused and skipped
  the `ltn/` folder (OPS-614 item). `caffeinate -i` does not keep a
  laptop out of Maintenance Sleep; two runs were lost to sleep.

## Timeline

All ET. Run 1 2026-11-03, run 3 2026-11-04; run 2 void (sleep).

- 22:33:44 capture recording. 22:34 first starts fail on the stale pair;
  pair refreshed.
- 22:35:03 LTN up; 22:35:06.9 scada up, link Active, `layout.lite`.
- 22:36:03, 22:37:04 LTN pings; 22:36:00, 22:37:00 report events acked.
- 22:37:29 LTN SIGTERM; 22:37:32 laptop sleeps. 22:53:02 wake; the
  scada's watchdog stops it (pat 1080 s ago, 630 allowed).
- 22:54 to 23:57 run 2, void: the machine slept through it.
- 00:02:25 LTN, 00:02:28 scada; 00:02:29.819 Active.
- 00:04:03 LTN SIGTERM. 00:05:05.019 `response_timeout`, one ping.
- 00:05:43 LTN again; 00:05:49.449 Active; reupload.
- 00:07:18 both stopped cleanly. 00:09 capture stopped (2099 messages).

## Analysis notes

- Times in `link-trace.jsonl` are the broker's capture time
  (`CapturedUnixMs`, laptop clock), inside a few ms of the scada's
  message-summary log times.
- `PeerName` on the scada's comm events is its local link name
  (`gridworks_mqtt`), not the LTN's alias.
- The 22:53 shutdown and the 22:54 to 23:57 window are artifacts of
  laptop sleep, not link behavior.

## Folder contents & experimental method

All data here was GENERATED by this run on the laptop's dev broker; none
of it is in the journal DB or the eventstore, and a re-run produces a new
dataset. The run started and stopped two laptop services (a sim scada
and the LTN) and touched nothing deployed.

- `README.md`, `runbook.md` (the commands as run, with wall clocks).
- `g.node.gt.json`: the dev LTN identity the LTN booted with.
- `run_legs.sh`: the scripted away-and-back timeline
  (`RUN=run3 caffeinate -dims ./run_legs.sh`).
- `trace_summary.py`: one line per scada–LTN message from a capture
  (`uv run python trace_summary.py captures/<file>.jsonl`).
- `reduce_capture.py` and `link-trace.jsonl`: the committed evidence, one
  compact row per scada–LTN message (bodies kept for the control words
  only). Regenerate: `uv run python reduce_capture.py captures/<file>.jsonl > link-trace.jsonl`.
- `captures/` (gitignored, 6 MB): the raw firehose capture and its
  provenance sidecar, the full evidence, on this laptop only.
- `logs/`: `clock.txt` (every step's wall clock) and `capture.log`;
  the scada and LTN stdout per run (`*.log`, 5 MB) stay gitignored on
  this laptop.
- `instances/`: the `gw.experiment.run` record.
