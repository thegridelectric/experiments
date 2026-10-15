# pico-power-cycling

> The fleet's pico reliability work, one folder per dated run under
> this one: how often the scadas' pico-cycler power-cycles the 5 V bus,
> why the picos flatline, and which firmware each pico runs. Undated
> because the question keeps coming back on new data; like
> `../beta-field-windows/`, this is an ongoing practice, not one
> experiment. The durable facts it has verified live in the
> gridworks-pico executor ("Verified field facts").

## Runs

- [2026-10-14-reboot-storm](2026-10-14-reboot-storm/) — analysis: bus
  reboots per house per day from the journal DB, 09-01 to 10-14, set
  against the per-box firmware upload history, then the mechanism from
  post times: the scada declares a tank pico missing after exactly its
  60 s post period, and the 2026-09-15 firmware sends about one sync
  post in five a second late. Every reboot, old firmware included,
  fires at 60.0x s since one tank pico's last post.
- [2026-08-05-link-census](2026-08-05-link-census/) — analysis,
  NEGATIVE result: MAC OUI cannot discriminate wired from wifi picos;
  ground truth is each pico's `comms_config.json`.
- [2026-08-03-gap-analysis](2026-08-03-gap-analysis/) — analysis:
  reporting gaps, zombie glitches and their Venn over 56 days; spruce's
  "flaky pico" was a feedback loop (permanent zombie, half-hourly bus
  shakes), confirmed by the floor2 removal and the wifi-herd reduction.

## Folder top

- `firmware-track-record.md` — which gridworks-pico build each house's
  picos received, and when, from the boxes' `code_uploaded/` folders
  (md5 of the served file matched to the commit). The place to extend
  at every reflash.
