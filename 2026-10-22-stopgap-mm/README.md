# stopgap-mm, 2026-10-22

> What this is: does the stopgap MarketMaker's `latest.price`, published
> once at the top of the hour on the maker's mic exchange, reach an
> MQTT-native LTN on the rjb topic within the first seconds of the hour
> and reach the journal? Asked twice on one day, on the laptop broker
> and then on hw1 with the maker on its own box. PASS both; the logbook
> line is the index record.

## Why

The LTN clears its dispatch contract against the price the MarketMaker
publishes at the top of the hour, and until this work each LTN fetched
a price for itself. The stopgap maker publishes one `latest.price` per
hour on AMQP; the LTN is MQTT-native and hears it only because the
broker's definitions bridge the maker's broadcasts to `amq.topic`. The
dev run proves the path before the production definitions are reloaded
and the box goes up; the hw1 run is the experiment the design's EDD
clause names, so its PASS is what makes the design Verified.

## Setup

**Dev run, laptop.** The dev stack per `../dev-stack-recipe.md`: broker
`gw-dev-rabbit` on the gwbase 0.6.1 image, whose baked definitions
have the `mmmic_tx → amq.topic (rjb.#)` tap; the journal DB and
journalkeeper, registry and weather already up and left as found. The
maker from `gridworks-marketmaker` `jm/stopgap-marketmaker` at
`3e28a96`, dev identity `d1.isone.me.versant.keene`, live ISO-NE login.
A dev LTN from `gridworks-scada` `jm/td-flo-latest-price` at `2647b3d8`
with the scada test-fixture layout and no scada peer. `mqtt_witness.py`
(this folder) subscribed on the broker's MQTT face to the maker's
topic. The maker's first tick published the open slot; the top of the
hour published the next.

**hw1 run.** The maker from `main` at `4ab796e` on the `mm` box, unit
`mm-rabbit`, identity `hw1.isone.me.versant.keene` from the registry's
served record, its own client cert, connected to the hw1 broker over
TLS; booted 19:15Z, no publish before the hour by design. The hw1
broker's definitions reloaded from gwbase `main` that afternoon with the
tap as the one new entry, drift check IN SYNC. Oak's LTN on the ltn box
(`td/generalized-flo` at `ebd498ff`, which has the latest-price merge)
as the MQTT-face listener, subscribed to
`rjb/hw1-isone-me-versant-keene/mm/latest-price`. The journal DB as
the store, with zero `latest.price` rows before the hour.

Nothing was stopped or held for either run. Neither LTN had a bid in
for its slot, and the maker drops bids.

## Found

PASS, three publishes, each heard by the LTN within 60 ms and in the
journal.

| run | slot (ET) | maker publish (UTC) | LTN "Received latest price" | journal row |
|---|---|---|---|---|
| dev, first tick | 11:00 | 15:47:55.068 | 15:47:55.074 | 15:47:55.073 |
| dev, top of hour | 12:00 | 16:00:00.004 | 16:00:00.046 | same path, not re-queried |
| hw1, top of hour | 16:00 | 20:00:00.183 | 20:00:00.241 | 20:00:05.800 |

- Prices: dev 11:00 slot LMP 26.06 + on-peak delivery 597.28 = 623.34
  USD/MWh; dev 12:00 LMP 25.55 + shoulder 70.34 = 95.89; hw1 16:00 LMP
  34.79 + on-peak 597.28 = 632.07. The three words are in `instances/`.
- Both LTNs decoded the bare word on the rjb topic and logged "Ignoring
  - no bid exists": the word reached the contract handler, which had no
  bid.
- The hw1 publish is inside the LTN's five-second window with 4.8 s to
  spare over the box-to-broker-to-ltn-box hops the dev run did not
  have.
- The hw1 journal row is 5.6 s behind the publish. That is the
  journalkeeper's own queue, not the bus: at every five-minute mark the
  fleet's `report.event`s cost its single message loop 1 to 3 s each,
  and the price waited behind four of them. The same spike is in the
  journal at every mark and a week earlier, so it predates the maker.
  OPS-616 is the design for it.
- The maker's message flips a peerless dev LTN's scada link from
  `awaiting_peer` to `active`, since the proactor counts any decoded
  message on a link as from that link's peer. Harmless with a scada
  present.

## Timeline

ET.

- 11:47 dev stack: witness, dev LTN and maker started; 11:47:55 first
  publish heard by all three.
- 12:00:00 dev top-of-hour publish; 12:00:41 maker, LTN and witness
  stopped.
- 12:51 hw1 broker definitions reloaded, `rmq1` restarted, nine
  connections back in 21 s.
- 13:40 to 14:45 `mm` box built, checkout at `4ab796e`, identity and
  `.env`.
- 15:14 cert minted; 15:15 `mm-rabbit` started, connection and
  principal confirmed.
- 15:47 oak LTN restarted on the ltn box with the latest-price code.
- 16:00:00.183 maker publish; 16:00:00.241 oak LTN receive;
  16:00:05.800 journal row.

## Analysis notes

- Dev-run clocks are all the laptop's; hw1 clocks are the mm box, the
  ltn box and the journal DB, all NTP. The LTN's receive time in the
  table is the ltn box's log, read as UTC from ET.
- The journal row's `timestamp` equals its `persisted_at` (the keeper
  stamps a header-less broadcast at persist), so the row cannot show
  the price's own lag; the 5.6 s is against the maker's log.
- A tap listener on the analytics broker was armed for the hw1 hour as
  a second bus-side witness and died on a heartbeat timeout when the
  laptop's connection dropped, twice. The maker's log and the journal
  row are the bus-side witnesses for hw1.
- The forced stale-fetch pass (ISO-NE unreachable, last price republished
  with a Critical glitch) was not run; it is covered by the maker's gate
  tests.

## Folder contents & experimental method

The hw1 journal row is the immutable store's own record, queried, not
copied. Everything else was GENERATED by the runs' own instruments: the
witness's arrival records and the service logs, read off their hosts.
Nothing in the running system was stopped or held; the hw1 broker
restart that afternoon was the deploy of the tap the run needed, not a
measurement step.

- `mqtt_witness.py` — the dev run's stand-in LTN: a paho subscriber
  that writes each arrival as one JSON line with its receive time. Run
  from the scada venv.
- `captures/dev-mqtt-witness.jsonl` — the two dev arrivals, untouched.
- `captures/hw1-journal-latest-price-rows.txt` — the journal's
  `latest.price` rows at 20:08Z, psql `-A` output.
- `logs/dev-ltn-excerpt.log`, `logs/hw1-oak-ltn-excerpt.log` — the LTN
  log lines around each receive; `logs/hw1-maker.log` — the maker's log
  on the box, verbatim.
- `instances/` — the three `latest.price` words as published, named
  `<maker alias>-<slot start>-latest.price-000.json`, and one
  `gw.experiment.run` per run (`dev-`, `hw1-`).

Regenerate the hw1 side (a re-run is the next hour's publish):

    ssh mm 'cat ~/.local/state/gridworks/marketmaker/log/*.log' > logs/hw1-maker.log
    ssh ltn 'grep -n -B12 -A2 "Received latest price" ~/ltn-oak/.local/state/gridworks/ltn/log/proactor.log' > logs/hw1-oak-ltn-excerpt.log
    psql "$DB_ANALYST_URL" -Atc "select id, timestamp, from_alias, persisted_at, payload::text from gridworks.messages where message_type_name='latest.price' order by timestamp" > captures/hw1-journal-latest-price-rows.txt

Regenerate the dev side (the dev stack per `../dev-stack-recipe.md`):

    python mqtt_witness.py rjb/d1-isone-me-versant-keene/mm/latest-price captures/dev-mqtt-witness.jsonl

No `gw.readings` instance here; no display CSV applies.
