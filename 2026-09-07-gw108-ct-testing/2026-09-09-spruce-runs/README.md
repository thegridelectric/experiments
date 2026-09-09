# 2026-09-09 spruce runs — which gw108 CT inputs are electrically one node

Status: Draft · Pass 0 · Updated 2026-09-09

Handoff for a fresh session: seven `peek.py` runs on the spruce gw108 with
the CT arrangement changed between runs. The evidence says three of the
four ADC inputs (P0, P1, P3) read one shared signal whichever of them
holds a CT, and the fourth (P2) is independent with a different bias.
The job for the next session is to explain that on the board and
propose the experiment that pins the cause. Nothing here is Verified;
the numbers are the raw peek output, the setup descriptions are as
recalled during the visit (George on site, Jessica running the script).

## Why

The scada needs a conclusive "secondary pump is on" signal (the hall
flow meters are believed clogged; `secondary-flow` reads 0 with water
moving). The gw108 has four CT inputs on an ADS1115 at 0x48, connectors
labeled CT1..CT4 mapping to ADC inputs P0..P3. Yesterday's `jump1`
showed P0 and P1 carrying the same signal with both pumps on. Today's
runs isolated one pump at a time and moved the CTs between connectors.

## Setup (common to all runs)

- **Board:** spruce gw108, ADS1115 at 0x48, single-ended P0..P3; P0 is
  the connector silk-labeled CT1 and carries a 470 Ω burden selected by
  a jumper (fitted throughout). Relays on the 0x21 expander drive the
  pumps (reg3 bit 5 secondary, bit 4 store, bit 2 iso valve).
- **CT2 ("the eGauge CT"):** eGauge voltage-output type, 1 A rating.
  Clamped where George found the secondary pump's conductor; he later
  found that conductor to be a return shared by both pumps (the CTs sit
  in a small box with wires from both the store and the secondary meter
  inside). Removed from the gw108 after run5 and attached to eGauge port
  05 (see "eGauge" below).
- **CT1 ("the blue CT"):** current-output type, 1 A, 2000:1, so with the
  470 Ω burden 235 mV rms per amp per pass. On the store pump conductor
  for runs 1–2 (leads on the CT1/P0 connector), clamp removed for runs
  3–5, back on the store pump for runs 6–7 with leads on P0.
- **Script:** `../peek.py` from the laptop; per run it stops the
  deployed scada and summer hack, holds the iso valve open, runs the
  secondary pump alone (bit 5) then the store pump alone (bit 4), 15 s
  hold, captures two channels each phase with the box's `capture.py`
  (2 s, 394 conversions/s), folds at the fitted mains frequency, and
  restores relays and services. `--channels A,B` names the secondary
  phase's own input first and the store phase's second. Unlimbo was
  brought down before every run; nothing else drove the 0x21 relays.
- **Verdict thresholds** (written for CT2's ~80 mV level, wrong for
  CT1's): own < 20 mV INCONCLUSIVE; other/own < 0.1 CLEAN; > 0.5
  MIRRORED; between PARTIAL.

## The runs

Instances are in `instances/`, tagged `p<n>.<phase>.run<k>` (28 files;
peek writes no fold pngs). Values are waveform rms mV / noise rms mV;
bias in V.

| run | CT2 (voltage type) | CT1 (blue current type) | channels | sec phase | store phase | verdicts |
| --- | --- | --- | --- | --- | --- | --- |
| run1 | on shared return, leads on **P1** | on store pump, leads on **P0**, jumper | P1,P0 | P1 83.5/5.9 · P0 79.4/6.2 · bias 1.628 both | P1 58.4/6.7 · P0 63.0/10.1 | MIRRORED 0.95 / MIRRORED 0.93 |
| run2 | same | clamp on store pump, **leads lifted off the board** | P1,P0 | P1 84.5/10.2 · P0 77.5/20.6 · bias 1.627/1.629 | P1 36.5/3.5 · P0 35.0/3.1 | MIRRORED 0.92 / MIRRORED 1.04 |
| run3 | moved to 4th connector, leads on **P3** | clamp removed from store pump, off the board | P3,P0 | P3 85.0/6.5 · P0 79.8/6.2 · bias 1.642 both | P3 36.1/3.1 · P0 34.8/2.9 | MIRRORED 0.94 / MIRRORED 1.04 |
| run4 | same (P3) | off | P3,P2 | P3 85.1/8.1 · P2 5.3/18.1 · bias 1.642 / **1.864** | P3 35.9/3.0 · P2 4.6/9.4 · bias 1.642 / **1.905** | CLEAN 0.06 / INCONCLUSIVE (P2 empty) |
| run5 | moved to 3rd connector, leads on **P2** | off | P3,P2 | P3 3.4/12.6 · P2 58.4/8.6 · bias 1.647/1.650 | P3 3.8/13.2 · P2 35.0/3.1 · bias 1.650 both | INCONCLUSIVE (P3 empty) / PARTIAL 0.11 (P3 is floor noise) |
| run6 | **removed from board** (to eGauge) | on store pump, leads on **P0**, one pass | P2,P0 | P2 5.1/8.7 · P0 **1.6/0.3** · bias 1.914/1.638 | P2 4.8/17.3 · P0 **17.4/0.8** · bias 1.873/1.638 | INCONCLUSIVE ×2 (threshold artifact; P0 is a real 17 mV) |
| run7 | removed | same, conductor **looped twice** through CT1 | P2,P0 | P2 5.5/17.2 · P0 1.6/0.4 · bias 1.875/1.638 | P2 4.3/17.7 · P0 **30.9/1.8** · bias 1.876/1.639 | INCONCLUSIVE / PARTIAL 0.14 (P2 is floor noise) |

Entry relay state was iso=1, store=0, secondary=1 for runs 1–5 and 7,
secondary=0 for run6 (services had been stopped by hand first). All
captures PASSed the sampler check (~394 conversions/s, gaps < 8 ms);
run2 P0-sec and run4 P2-store ran at ~half rate (240/s) with no visible
effect on the fold.

## What the runs say

1. **P0, P1 and P3 read one signal.** With CT2 alone on P1 (run2, CT1
   leads off), P0 carried 77.5 mV against P1's 84.5. With CT2 alone on
   P3 (run3), P0 with nothing attached carried 79.8 against 85.0. Bias
   was identical on the tied inputs in every run and moved together
   (1.628 → 1.642 V) when CT2 changed connectors.
2. **P2 is not part of that node.** Run4: P2 with nothing attached read
   5 mV with no 60 Hz lock while P3 read 85. Run5: CT2 on P2 read 58
   (sec) and 35 (store) while P3, empty, read 3–4 mV. P2's bias floats
   (1.86–1.91 V, drifting) with nothing attached and sits at 1.65 V with
   a CT on it; the tied three hold 1.638–1.642 V regardless.
3. **The voltage-type CT was the noise source.** Every run with CT2 on
   the board had a 6–20 mV noise floor on the tied node; with it gone
   (runs 6–7) the floor on P0 fell to 0.3–1.8 mV.
4. **CT1 reads the store pump cleanly and small:** 17.4 mV one pass,
   30.9 mV two passes (×1.78), off state 1.6 mV, so ~66–74 mA, roughly
   8–9 W at 120 V, an ECM circulator on its lowest setting. It does not
   see the secondary pump (1.6 mV in every sec phase).
5. **CT2 saw the store pump in every store phase (35–36 mV)** wherever it
   sat, consistent with George's shared-return finding. But on the
   eGauge (below) the same CT on the same conductor reads 0 W with the
   store pump alone, so what the gw108 saw may be pickup rather than
   conduction. Unresolved.
6. The **sec-phase level differed by connector** for the same CT: ~85 mV
   on P1/P3, 58 mV on P2. The store-phase level did not (36 vs 35).
   Unexplained; could be input-network differences or pump-draw
   variation between runs.

## eGauge side (context, not part of the board question)

CT2 was moved to eGauge port 05, configured as a 5 A CT (it is 1 A, so
watts read ×5), register renamed `05-secondary-pump`; both tlayouts lines
now carry `secondary-pump-pwr` at Modbus 9008 (replacing `dist-pump-pwr`).
Result: secondary pump on = 184–199 W indicated (≈37 W real), off = 0 W;
store pump alone = 0 W. Nine clean on/off transitions observed. After the
eGauge settings save the meter reported 0 W on every register for ~9 min
(counters frozen); a reboot from its Tools page cleared it. Jessica: this
has happened before ("shows its channel checker screen but nothing
else").

## The schematic (read this first)

`gridworks-hardware/PCBs/KiCad/FullScada1/Gw108_RevB/ADC.kicad_sch` is the
CT/thermistor sheet of the ordered board (`e4de4c3` "Order submitted for
RevB"; `Gw108_RevC/` is a placeholder copy). Not yet traced net by net;
what a text pass over the sheet shows:

- three `ADS1115IDGS`; nets `CT1`..`CT4`, `THERMISTOR1`..`4`, `I2C_SDA/SCL`,
  and a single bias net **`1V65`**;
- four `R470 1%` (the burdens) with four `Jumper_2_Small_Bridged` (JP1–4,
  the burden jumpers, bridged by default); four `4k7`, four `330R`, four
  `5k6 0.1%`, two `100k 1%`, four `10uF`, six `100nF`, nine Schottky
  clamps, `8P Terminals` ×2 (the CT and thermistor connectors), test
  points.

The hypothesis that fits all seven runs: **the four CT inputs are
referenced to one `1V65` node, derived from the two 100k resistors (a
50 kΩ source), and every CT's signal current returns through that node,
so it modulates the reference every input rides on.** That is what a
"tied" P0/P1/P3 looks like (identical bias, moving together when CT2
changed connectors; the voltage-type CT's noise on all of them). P2 (CT3)
would then be the *broken* one: its link to `1V65` open (a missing or
unpopulated part, or a layout gap), which is why it floats at 1.86–1.91 V
with nothing attached, sits at 1.65 V only when a CT provides the DC
path, and does not carry the shared signal. If the 10 µF parts are meant
to decouple `1V65` (265 Ω at 60 Hz, which would have suppressed this),
check whether they are on that net and populated.

What to do with it: trace `1V65` on the sheet and the PCB (`.kicad_pcb`),
list what connects to it and whether CT3's path differs; then the bench
continuity check below distinguishes trace/bridge from shared-reference.
The fix, if this holds, is a buffered or low-impedance `1V65` (op-amp
follower or a proper decoupling cap), a board change, not wiring.

## Open questions for the next session

- What ties P0, P1 and P3 on the gw108: a shared trace, a solder bridge
  across the ADS1115 inputs (A0/A1/A3 are not all adjacent), or the
  input networks sharing one node (a common burden/bias net for three
  connectors)? Read the gw108 schematic / board file (Jessica has it)
  before proposing hardware probing.
- Why P2 differs: separate bias network, missing bias, or the only
  correctly built input? Its floating bias (1.86–1.91 V) is not the
  1.64 V mid-rail of the others.
- Whether the same tie exists on the honeysuckle bench gw108 (a second
  board of the same build) — a bench run needs no site visit.
- Whether the "shared return" pickup of the store pump on CT2 was
  conduction or magnetic pickup in the CT box.

## Proposed experiments (sketches; the next session decides)

- **Bench continuity, board unpowered:** ohmmeter between the signal
  pins of CT1/CT2/CT4 connectors and against CT3; expect near-zero on
  the tied set if it is a trace/bridge, hundreds of Ω to kΩ if it is a
  shared bias net.
- **One CT, four channels, honeysuckle:** a current CT with the burden
  jumper on P0 only, capture P0..P3 in one phase (extend `peek.py` to
  four channels or call `capture.py` directly). Reproduces today's
  finding without a site visit and gives all four biases.
- **Injected known signal:** the `synth.py` path already in the parent
  folder can drive a known 60 Hz level into one input; measure the
  transfer to each other input.

## Practical notes

- The box's `~/experiments` clone must be pulled after this rename
  (`peek.py` BOX_DIR follows it); the box runs pushed SHAs only.
- `peek.py --channels` is new today (uncommitted at handoff with this
  README).
- `../README.md` "One pump at a time" holds the verdict rules and the
  two earlier spruce runs (`jump1`, `base1`, 2026-09-08).
