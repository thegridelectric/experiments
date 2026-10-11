# Evidence provenance

- `spruce-window-boot.log` — the window scada's stdout/stderr on spruce (`/tmp/spruce-window/boot.log`), copied by `spruce_window.sh off` at 11:05:01 ET; header line added, body untouched.
- `capture.jsonl` — `capture_broker.py` on the laptop's gw-dev-rabbit, vhost `d1__1`, started 10:49:26 ET by `spruce_window.sh on`, stopped 11:05 ET by `house_window.sh capture off`; 51 messages, wire bodies untouched (one JSON object per line, `RoutingKeys` as published).
- `events/` — the 10 event files the window scada persisted on the box under `~/.local/share/gridworks/scada-experiment/event/` stamped after the window start, pulled by `off`; wire data untouched.

Run 2 (`run2/`):

- `spruce-window-boot.log` — `/tmp/spruce-window/boot.log` on spruce, copied by `spruce_window.sh off` at 15:59:21 ET; header line added, body untouched.
- `beech-window-boot.log`, `beech2-window-boot.log` — `/tmp/beech-window/boot.log` on beech and on beech2 (run 2b, 15:37:54–15:58), copied by `beech_window.sh off` at 15:59:40 / 15:59:48 ET; header line added, bodies untouched.
- `beech-window-boot-2a-early-close.log` — the same on beech for run 2a (15:31:04–15:37:14, closed by hand), copied by `off` at 15:37:20 ET; header line added.
- `capture.jsonl.gz` — `capture_broker.py` on the laptop's gw-dev-rabbit, started 15:29:18 ET by `spruce_window.sh on`, shared by both houses' windows, stopped 16:00 ET by `house_window.sh capture off`; 166 messages, wire bodies untouched; gzipped (`gzip -n -9`) because the plain file is 2.5 MB, over the repo's 2 MB cap, and `gzip -dc` gives back the captured bytes.
- `events-spruce/`, `events-beech/`, `events-beech-2a/` — the event files each window scada persisted on its box under `~/.local/share/gridworks/scada-experiment/event/` stamped after the window start, pulled by `off`; wire data untouched.
