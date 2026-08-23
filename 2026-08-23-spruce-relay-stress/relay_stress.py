#!/usr/bin/env python3
"""relay_stress — field reproducer for the 0x21 TCA9555 reset under relay
switching (the 2026-08-20 observation: rapid iso-valve toggling brings the
classic OPS-452 power-on-reset, possibly worse with more 0x21 coils energized).

Hypotheses, each a separate sweep axis (env-driven; see KNOBS):
  H1  toggle PERIOD — faster iso toggling resets more (coil-switching
      transients / supply droop).
  H2  LOAD — more 0x21 coils held energized resets more (standing current
      sags the rail so a transient crosses the POR threshold).
  H3  SPACING — two different coils commanded back-to-back resets more than
      the same two commanded SPACING seconds apart (the candidate software
      mitigation: serialize relay commands with a minimum gap).

Posture throughout (agreed with JM 2026-08-23):
  secondary pump ON (cooling continues; DAC untouched — it holds its value),
  CHARGE valve ENERGIZED (the secondary pump always has a path, so a closed
  iso valve never dead-heads it), STORE pump DE-ENERGIZED, elements never
  touched. Toggle targets: iso valve (wired, the 08-20 reproducer), hp-call
  (the Samsung ignores the contact right now). Load relays: the UNWIRED 0x21
  positions — boiler-buffer-valve, boiler-intercept, misc1, misc2,
  primary-pump — energizing them moves nothing in the house.

Each phase = one (target, period, load_count, spacing) cell: perform TOGGLES
toggles; after every write read both config registers (POR signature =
nonzero, confirmed by a second read 0.3 s later so a garbled read can't
fake a reset). On a reset: CRITICAL + full register snapshot, re-init 0x21
(clear-then-configure), re-assert the posture + load, keep counting. A phase
stops early at MAX_RESETS_PER_PHASE. Results: per-phase line in the log and
a JSON summary (`relay-stress-<run>-results.json`) for the experiment folder.

Lives in the experiments folder; runs ON spruce from the box's
`~/experiments` checkout with the summer hack STOPPED (single writer on
0x21). Every run is named on the command line (`--run A`) and writes two
files to OUT_DIR (`/home/pi/relay-stress-runs/`): `relay-stress-<run>.log`
(every write, every reset with its register snapshot) and
`relay-stress-<run>-results.json` (typed per-phase records + knobs + the
run window). Exact per-run commands are in the folder README.

Posture knobs (env): CHARGE_POSTURE / PUMP_POSTURE / HP_POSTURE (1/0) set
the coils that are NOT being toggled; LOADS sets how many of the unwired
coils are energized. On any exit: loads OFF, hp-call 0, store-pump 0, iso
OPEN, secondary pump ON, charge valve OFF — then restart the hack.

Relay addresses are hand-coded from starter-scripts/gw108_test_code.py (the
authored board map): the deployed spruce layout carries no gw108 relay
nodes yet — the missing words are the `i2c.relay.component.gt` nodes the
spruce-unlimbo relay port emits; when they land, read (chip, port, bit)
from the box's layout instead.
"""

import argparse
import itertools
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

import smbus2

# -----------------------------
# KNOBS (env-driven so a field run is a launch line, git stays the record)
# -----------------------------
# Comma list of coils to toggle each cycle, in order: any of iso, hp, charge,
# pump ("both" = iso,hp). SPACING is the gap between successive coils in one
# cycle. A coil NOT in the list holds its posture value (iso OPEN, hp 0,
# charge ENERGIZED, pump ON) — so toggling charge with iso open never
# dead-heads the pump; toggling pump blips cooling for <= PERIOD seconds.
TARGET = os.environ.get("TARGET", "iso")
PERIODS = [float(x) for x in os.environ.get("PERIODS", "0.3,1,3").split(",")]
LOADS = [int(x) for x in os.environ.get("LOADS", "0,5").split(",")]
SPACINGS = [float(x) for x in os.environ.get("SPACINGS", "0").split(",")]
TOGGLES = int(os.environ.get("TOGGLES", "30"))     # per phase
MAX_RESETS_PER_PHASE = int(os.environ.get("MAX_RESETS", "3"))
SETTLE_BETWEEN_PHASES_S = float(os.environ.get("SETTLE", "10"))
CONFIRM_S = 0.3
OUT_DIR = Path(os.environ.get("OUT_DIR", "/home/pi/relay-stress-runs"))
ET = ZoneInfo("America/New_York")


class PhaseResult(NamedTuple):
    """One sweep cell. Kind-specific result record (no sema word covers a
    relay-stress phase; missing word: a `gw.relay.stress.phase` stats word —
    coin it once a second experiment kind wants reset-count-per-cell).
    target: which coil(s) toggled; period_s: seconds between toggles;
    load: number of unwired 0x21 coils held energized; spacing_s: gap
    between the iso and hp commands when target=both; toggles: toggles
    performed; resets: confirmed POR signatures; first_reset_toggle: toggle
    index of the first reset (None if none); pin_mismatch: toggles after
    which an input-register readback disagreed with the command;
    elapsed_s: phase wall-clock; start/end_unix_ms: phase window."""
    target: str
    period_s: float
    load: int
    spacing_s: float
    toggles: int
    resets: int
    first_reset_toggle: int | None
    pin_mismatch: int
    elapsed_s: float
    start_unix_ms: int
    end_unix_ms: int

EXPANDER = 0x21
# (label, register, bit) — per gw108_test_code.py
HP_CALL = ("hp-call", 2, 0)
ISO_VALVE = ("iso-valve", 3, 2)
CHARGE_VALVE = ("charge-valve", 3, 3)     # silk "DISCHARGE VALVE"
STORE_PUMP = ("store-pump", 3, 4)
SECONDARY_PUMP = ("secondary-pump", 3, 5)
LOAD_RELAYS = [                           # UNWIRED at spruce (JM 2026-08-23)
    ("boiler-buffer-valve", 2, 3),
    ("boiler-intercept", 2, 4),
    ("misc-relay1", 2, 5),
    ("misc-relay2", 2, 6),
    ("primary-pump", 2, 7),
]
ISO_OPEN = 1
TOGGLE_COILS = {"iso": ISO_VALVE, "hp": HP_CALL, "charge": CHARGE_VALVE,
                "pump": SECONDARY_PUMP}
# CHARGE_POSTURE=0 runs with the charge-valve relay de-energized (the 12:36
# finding: energized = no resets; de-energized = resets on most transitions).
POSTURE = {"iso": ISO_OPEN,
           "hp": int(os.environ.get("HP_POSTURE", "0")),
           "charge": int(os.environ.get("CHARGE_POSTURE", "1")),
           "pump": int(os.environ.get("PUMP_POSTURE", "1"))}


def target_list(target: str) -> list[str]:
    names = ["iso", "hp"] if target == "both" else target.split(",")
    unknown = [n for n in names if n not in TOGGLE_COILS]
    if unknown:
        raise SystemExit(f"unknown TARGET coil(s) {unknown}; choose from {list(TOGGLE_COILS)}")
    return names

# -----------------------------
# Logging — per-run file in OUT_DIR, configured in main() once --run is known
# -----------------------------
logger = logging.getLogger("relay-stress")
logger.setLevel(logging.INFO)


def setup_logging(run: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / f"relay-stress-{run}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.StreamHandler(), logging.FileHandler(log_path)):
        h.setFormatter(fmt)
        logger.addHandler(h)
    return log_path


bus = smbus2.SMBus(1)
resets_total = 0


# -----------------------------
# Expander primitives
# -----------------------------
def i2c_retry(fn, what: str, tries: int = 4):
    """The chip stops ACKing for up to ~1 s while it browns out; a bare
    OSError there would kill the run mid-repair (run B, 14:16). Retry with a
    1 s pause, logging each miss; give up (raise) only after `tries`."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except OSError as e:
            logger.critical(f"I2C ERROR during {what} (attempt {attempt}/{tries}): {e}")
            if attempt == tries:
                raise
            time.sleep(1.0)


def set_bit(relay, value: int) -> None:
    _, reg, bit = relay

    def rmw():
        s = bus.read_byte_data(EXPANDER, reg)
        s = s | (1 << bit) if value else s & ~(1 << bit)
        bus.write_byte_data(EXPANDER, reg, s)
    i2c_retry(rmw, f"set {relay[0]}->{value}")


def get_pin(relay) -> int:
    _, reg, bit = relay
    return (i2c_retry(lambda: bus.read_byte_data(EXPANDER, reg - 2),
                      f"pin read {relay[0]}") >> bit) & 1


def cfg_nonzero() -> bool:
    return (bus.read_byte_data(EXPANDER, 6) != 0
            or bus.read_byte_data(EXPANDER, 7) != 0)


def snapshot() -> str:
    try:
        return " ".join(f"r{r}={bus.read_byte_data(EXPANDER, r):08b}"
                        for r in (0, 1, 2, 3, 6, 7))
    except OSError as e:
        return f"read failed: {e}"


def init_expander() -> None:
    def clear_then_configure():
        for reg in (2, 3, 6, 7):
            bus.write_byte_data(EXPANDER, reg, 0x00)
    i2c_retry(clear_then_configure, "init_expander")


def reset_check(context: str) -> bool:
    """True if a confirmed POR signature is present (and repaired)."""
    global resets_total
    try:
        nz = cfg_nonzero()
    except OSError as e:                  # chip not ACKing = browning out right now
        logger.critical(f"I2C ERROR {context}: {e} — treating as reset")
        time.sleep(1.0)
        nz = True
    if not nz:
        return False
    snap1 = snapshot()
    time.sleep(CONFIRM_S)
    if not i2c_retry(cfg_nonzero, "confirm re-read"):
        logger.warning(f"config-reg glitch (not a reset) {context}: {snap1}")
        return False
    resets_total += 1
    logger.critical(f"RESET #{resets_total} {context} REGISTERS: {snap1}")
    time.sleep(0.5)                       # let the brownout pass before repairing
    init_expander()
    return True


# -----------------------------
# Posture
# -----------------------------
def assert_posture(load_count: int, state: dict[str, int]) -> None:
    set_bit(SECONDARY_PUMP, state["pump"])
    set_bit(CHARGE_VALVE, state["charge"])
    set_bit(STORE_PUMP, 0)
    for i, r in enumerate(LOAD_RELAYS):
        set_bit(r, 1 if i < load_count else 0)
    set_bit(ISO_VALVE, state["iso"])
    set_bit(HP_CALL, state["hp"])


def restore_exit_posture() -> None:
    for r in LOAD_RELAYS:
        set_bit(r, 0)
    set_bit(HP_CALL, 0)
    set_bit(STORE_PUMP, 0)
    set_bit(ISO_VALVE, ISO_OPEN)
    set_bit(SECONDARY_PUMP, 1)
    time.sleep(1)
    set_bit(CHARGE_VALVE, 0)
    logger.info("exit posture: loads OFF, hp-call 0, store-pump 0, iso OPEN,"
                " secondary-pump ON, charge-valve OFF. Restart the hack:"
                " sudo systemctl start spruce-summer-hack")


# -----------------------------
# One phase
# -----------------------------
def run_phase(target: str, period: float, load_count: int, spacing: float) -> PhaseResult:
    label = f"target={target} period={period}s load={load_count} spacing={spacing}s"
    logger.info(f"=== PHASE {label}: {TOGGLES} toggles ===")
    names = target_list(target)
    state = dict(POSTURE)
    assert_posture(load_count, state)
    time.sleep(2)
    reset_check(f"[pre-phase {label}]")
    resets = 0
    first_reset_toggle = None
    pin_mismatch = 0
    t0 = time.monotonic()
    start_ms = int(time.time() * 1000)
    n = 0
    for n in range(1, TOGGLES + 1):
        for i, name in enumerate(names):
            if i > 0 and spacing > 0:
                time.sleep(spacing)
            state[name] ^= 1
            set_bit(TOGGLE_COILS[name], state[name])
            if reset_check(f"[{label} toggle {n} after {name}->{state[name]}]"):
                resets += 1
                first_reset_toggle = first_reset_toggle or n
                assert_posture(load_count, state)
        if any(get_pin(TOGGLE_COILS[k]) != v for k, v in state.items()):
            pin_mismatch += 1
        if resets >= MAX_RESETS_PER_PHASE:
            logger.warning(f"phase stopped early at toggle {n}: {resets} resets")
            break
        time.sleep(period)
    elapsed = time.monotonic() - t0
    result = PhaseResult(
        target=target, period_s=period, load=load_count, spacing_s=spacing,
        toggles=n, resets=resets, first_reset_toggle=first_reset_toggle,
        pin_mismatch=pin_mismatch, elapsed_s=round(elapsed, 1),
        start_unix_ms=start_ms, end_unix_ms=int(time.time() * 1000),
    )
    logger.info(f"PHASE RESULT {json.dumps(result._asdict())}")
    assert_posture(load_count, dict(POSTURE))  # back to posture between phases
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="gw108 0x21 relay stress sweep")
    ap.add_argument("--run", required=True,
                    help="run label (e.g. A); names the log + results files")
    ap.add_argument("--yes", action="store_true", help="skip the hack-stopped prompt")
    args = ap.parse_args()
    target_list(TARGET)  # validate before touching anything
    log_path = setup_logging(args.run)
    results_path = OUT_DIR / f"relay-stress-{args.run}-results.json"
    if not args.yes:
        print("Stop the summer hack first:  sudo systemctl stop spruce-summer-hack")
        if input("Confirm spruce-summer-hack is STOPPED [type yes]: ").strip() != "yes":
            print("Aborted.")
            return
    # direction only — never clears 0x20; 0x21 values are re-asserted below
    bus.write_byte_data(EXPANDER, 6, 0x00)
    bus.write_byte_data(EXPANDER, 7, 0x00)
    cells = list(itertools.product(PERIODS, LOADS, SPACINGS))
    logger.info(f"relay_stress run {args.run}: TARGET={TARGET} PERIODS={PERIODS}"
                f" LOADS={LOADS} SPACINGS={SPACINGS} TOGGLES={TOGGLES}"
                f" posture={POSTURE} ({len(cells)} phases)."
                f" Baseline registers: {snapshot()}. Log: {log_path}")
    results: list[PhaseResult] = []
    run_start_ms = int(time.time() * 1000)
    try:
        for period, load, spacing in cells:
            results.append(run_phase(TARGET, period, load, spacing))
            time.sleep(SETTLE_BETWEEN_PHASES_S)
    except KeyboardInterrupt:
        logger.info("interrupted")
    finally:
        restore_exit_posture()
        run_end_ms = int(time.time() * 1000)
        # dict form appears once, here, at the serialization boundary
        results_path.write_text(json.dumps({
            "Run": args.run,
            "StartUnixMs": run_start_ms, "EndUnixMs": run_end_ms,
            "Knobs": {"TARGET": TARGET, "PERIODS": PERIODS, "LOADS": LOADS,
                      "SPACINGS": SPACINGS, "TOGGLES": TOGGLES,
                      "MAX_RESETS": MAX_RESETS_PER_PHASE, "POSTURE": POSTURE},
            "Phases": [r._asdict() for r in results],
        }, indent=2))
        logger.info(f"RESULTS ({resets_total} resets total) -> {results_path}")
        for r in results:
            logger.info(f"  period={r.period_s}s load={r.load}"
                        f" spacing={r.spacing_s}s -> resets {r.resets}"
                        f"/{r.toggles} (first at {r.first_reset_toggle})")
        fmt = lambda ms: datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d %H:%M:%S %Z")
        logger.info(f"ACTUATION WINDOW: {fmt(run_start_ms)} -> {fmt(run_end_ms)}"
                    f" ({run_start_ms} -> {run_end_ms} unix ms)")


if __name__ == "__main__":
    main()
