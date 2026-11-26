# mm-induced-traces, 2026-11-24

> What this is: the two marketmaker executor clauses the field has never
> produced, induced on the dev broker and recorded as trace vectors
> (OPS-617): a message addressed to the maker's inbox (hub 1b, inbox 1a)
> and a slot whose price never comes with nothing published before
> (gate 3c). Verdict: PASS on both; the window is the vector
> `wiki/gridworks-marketmaker/executor/traces/2026-11-25-dev-cold-failure-and-inbox`.

## Why

The executor's Vectors table had four rows with no Path. Boot mid-slot
(gate 1b) is in the first-hour field trace already, since the replayed
maker starts inside a slot. The other three cannot come from the field:
no message has ever reached the maker's inbox (the LTN's bids stop at
`amq.topic`; the fabric has no binding into `mm_tx`), and the maker has
never gone a whole slot with no price at a cold start. The recipe says
to induce such a window against the built service and record it, marked
induced, until a field window replaces it.

## Setup

Laptop, `d1` universe, `gw-dev-rabbit` (AMQP 5672, vhost `d1__1`).

- **The maker**: `gwmm rabbit` from `gridworks-marketmaker` at
  `b19764c` (`jm/price-at-slot-open`), gridworks-base 0.7.3, the dev
  identity `scripts/dev-g.node.gt.json` (`d1.isone.me.versant.keene`).
  The maker reads only the repo's own `.env` (its CLI finds it from the
  package, whatever the working directory), so the two values this run
  changes went in the process environment: `GWMM_ISONE_LOCATION_ID=99999`,
  a location ISO-NE does not have, so every ask fails as gate 2b states
  (the body is not a price for the maker's location); `GWMM_LOG_TZ=UTC`.
  The ISO-NE login is the repo's.
- **The capture**: `capture_broker.py` on the vhost's firehose, started
  before the maker.
- **The injection**: `inject.py` in this folder publishes one message on
  `ltnmic_tx` with the direct key `rj.<ltn alias>.ltn.bid.mm.<maker alias>`,
  the key the maker's queue is bound to through `ltnmic_tx -> mm_tx`. The
  body is a real `bid` 000 the oak LTN sent on 2026-11-11, the payload
  of eventstore key
  `hw1__1/eventstore/20261111/hw1.isone.me.versant.keene.oak-bid-1794358691720-hw1.ear.json`
  (the field bid travels inside a `gw` envelope on MQTT; the maker's
  inbox takes the bare instance). Nothing in this folder writes an
  instance by hand.

Nothing deployed was touched. The journal is not on the dev broker, so
the window is the capture and the maker's log.

## Protocol as run

1. Start the capture; wait for `capturing`.
2. Start the maker inside the open slot (20:41:53 ET, slot 20:00); its
   first tick passes that slot over.
3. Address the bid to the maker; read the maker's log and the queue.
4. Let the 21:00 ET slot open with every ask failing; wait past the
   240 s deadline for the glitch.
5. Stop the maker, then the capture.

## Found

PASS, both clauses as the executor states them.

- **Inbox drop (hub 1b, inbox 1a).** The bid published at
  01:43:37.798Z; the maker logged `dropped bid from
  hw1.isone.me.versant.keene.oak.ltn: the stopgap maker answers nothing`
  at 01:43:37.800Z; the queue went back to 0 messages (acked); nothing
  went out on the mic because of it. The body was never decoded (the
  log names type and sender, from the routing key).
- **Cold failure (gate 3c).** Slot 1795572000 opened at 02:00:00Z with
  nothing published in the run. No Provisional went out (a cold maker
  has no last parts). Every ask failed on the location. At 02:04:00.239Z
  (CreatedMs, 240 s after the slot's start) one `glitch` 000 went out on
  `mmmic_tx`, key `rjb.d1-isone-me-versant-keene.mm.glitch`: `Type`
  Critical, `Node` gate, `Summary` "no price to publish", `Details`
  naming the slot, the deadline and the failure. No `latest.price` in
  the whole window.

The glitch's `Details` text is the log Boundaries row's: free in a
replay past the slot number.

## Timeline (ET, 2026-11-24)

- 20:40:22 capture connected.
- 20:40:43 first maker start fails: the folder's own `.env` was not
  read (the CLI finds the repo's). Folder `.env` removed; values moved to
  the process environment.
- 20:41:53 maker started, slot 20:00 open, passed over.
- 20:43:37.8 bid addressed to the maker; dropped and logged 2 ms later.
- 21:00:00 slot 1795572000 opens; asks begin, each failing.
- 21:04:00.2 glitch "no price to publish" on the mic.
- 21:04:45 maker stopped; 21:05:06 capture stopped, 2 messages.

## Analysis notes

- The maker ran the two-stage gate (`jm/price-at-slot-open`). Both
  recorded clauses are version-independent in what they say: the inbox
  drop has no gate in it, and a cold failure publishes no stage. The
  deadline instant (240 s) is the executor's `fetch_deadline_s`; the
  deployed maker (`db25c3f`) raises the same glitch at the top of the
  hour instead, because it fetches once before the slot and has no
  deadline.
- `CapturedUnixMs` is the laptop clock at the firehose; the glitch's
  `CreatedMs` is the maker's clock 10 ms earlier, same machine.

## Folder contents & experimental method

All data here was GENERATED by this run on the laptop's dev broker; none
of it is in the journal or the eventstore, and a re-run is a new
dataset. The one input, the bid body, came from the S3 eventstore and
is re-pullable by its key above.

- `README.md` — this record.
- `inject.py` — addresses one instance file to the maker on the dev
  broker; prints the publish instant.
- `wire-in/hw1.isone.me.versant.keene.oak-bid-1794358691720-hw1.ear.json`
  — the eventstore object as fetched (the `gw` envelope).
- `wire-in/hw1.isone.me.versant.keene.oak-bid-000.json` — its payload,
  the body sent.
- `captures/broker-capture-20261124-204022.jsonl` and its
  `.provenance.txt` — the firehose capture, 2 messages, untouched.
- `logs/` — `maker.log` (stdout), `maker-start.txt`, `maker-stop.txt`,
  `inject.txt`, `capture.log`. The maker's own log is the gwbase
  rotating file `~/.local/state/gridworks/marketmaker/log/d1.isone.me.versant.keene.log`;
  the window's two lines are quoted in Found.
- `instances/mm.induced.traces-gw.experiment.run-001.json` — the run,
  emitted by `emit_instances.py`.

Regenerate the instance:

    uv run python 2026-11-24-mm-induced-traces/emit_instances.py

Re-run the window (a new dataset), from `experiments/`, with the
maker started from its repo under the two environment values above:

    uv run python capture_broker.py 2026-11-24-mm-induced-traces/captures
    uv run python 2026-11-24-mm-induced-traces/inject.py 2026-11-24-mm-induced-traces/wire-in/hw1.isone.me.versant.keene.oak-bid-000.json --type bid --from hw1.isone.me.versant.keene.oak.ltn
