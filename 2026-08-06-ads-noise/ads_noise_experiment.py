#!/usr/bin/env python3
"""ADS1115 noise-floor experiment (spruce, thermistor ADS 0x49 ONLY).

Question: what do faster reading + smoothing (the retired tsnap precedent)
and slower in-chip data rates each buy against the current reader baseline?

Three modes, run back to back on the four wired zone thermistors:
  base-128sps-1hz   single-shot 128 SPS, 1 Hz poll, raw       (current reader)
  fast-5hz-ema      single-shot 128 SPS, 5 Hz poll, EMA a=0.2 (tsnap precedent)
  slow-8sps-1hz     single-shot 8 SPS,   1 Hz poll, raw       (in-chip integration)

Per channel per mode: mean/stddev/p2p microvolts, mean temp and temp stddev.
The read path's facts — ADS address, reference volts, series resistance,
per-channel beta, and the AdcChannel -> ChannelName map — come from the
box's own hardware layout (the i2c.thermistor.reader.component.gt record in
LAYOUT_PATH), not from constants here; the layout-derived values are echoed
into a "board" section of the summary output as provenance. TempCalcMethod
is asserted SimpleBeta before that formula is applied.

The reader record is decoded through the generated sema snapshot
(../src/gwexp/sema) when possible — schema + axiom validation at decode,
no auto-upgrade (001/002 records carry the electrical constants; the 003
shape moves them to the device type and is not wired yet). Pre-registry
000 records (the fleet today) fall back to a legacy dict-walk. Which path
ran is recorded in the board provenance as "decode".
Readback-gated like the scada reader: the conversion register is trusted only
after the config register reads back equal to the written word.

Every sample is also written raw to RAW_PATH as one JSONL line
{t, mode, chan, uv[, ema_uv][, err]} — t is epoch seconds, uv the unfiltered
reading, ema_uv the filter output where the mode has one. Errors get their
own timestamped line. The summary JSON keeps its previous shape.

Touches ONLY address 0x49 (config + conversion regs). Big-endian block ops.
Run with the deployed scada STOPPED (one ADS reader at a time).
"""

import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

CONVERSION_REG = 0x00
CONFIG_REG = 0x01
FULL_SCALE = 4.096
T0 = 298.15
R0_KOHMS = 10

LAYOUT_PATH = os.path.expanduser(
    os.environ.get("LAYOUT_PATH", "~/.config/gridworks/scada/hardware-layout.json")
)


def _find_thermistor_reader(node):
    """Walk the layout for the i2c thermistor reader component record."""
    if isinstance(node, dict):
        if node.get("TypeName") == "i2c.thermistor.reader.component.gt":
            return node
        for v in node.values():
            found = _find_thermistor_reader(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_thermistor_reader(v)
            if found is not None:
                return found
    return None


def _snapshot_decode(node):
    """Decode the reader record through the generated sema snapshot.

    Returns (record-as-plain-dict, decode-label) on success, or
    (None, why-fallback). No auto-upgrade: a 001/002 instance carries the
    electrical constants; the 003 shape moves them to the device type
    (dereferenced via AdcName), which is not wired until the sema layout
    deploys — refuse loudly rather than guess."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    try:
        from gwexp.sema.codec import SemaCodec
    except ImportError as e:
        return None, f"legacy-dict-walk (snapshot unavailable: {e.__class__.__name__})"
    try:
        decoded = SemaCodec().from_dict(dict(node), auto_upgrade=False)
    except ValueError as e:
        return None, f"legacy-dict-walk ({e})"
    if not hasattr(decoded, "adc_address"):
        raise SystemExit(
            f"reader record {node['Version']} carries no electrical constants "
            "(they live on the device type at 003) — device-type dereference "
            "is not wired yet; run against a pre-003 layout"
        )
    return decoded.to_dict(), f"sema-snapshot ({node['TypeName']}/{node['Version']})"


_layout_bytes = open(LAYOUT_PATH, "rb").read()
_reader = _find_thermistor_reader(json.loads(_layout_bytes))
if _reader is None:
    raise SystemExit(f"no thermistor reader record found in {LAYOUT_PATH}")
_decoded, _decode_label = _snapshot_decode(_reader)
if _decoded is not None:
    _reader = _decoded
if _reader["TempCalcMethod"] != "SimpleBeta":
    raise SystemExit(f"unexpected TempCalcMethod {_reader['TempCalcMethod']!r}")

ADDR = _reader["AdcAddress"]
V_REF = _reader["AdcReferenceVolts"]
R_SERIES_KOHMS = _reader["SeriesResistanceKOhms"]

# A pin carries one config per published channel (-gw-temp and
# -gw-microvolts share the AdcChannel); collapse to one zone per pin and
# insist the pair agrees.
CHANNELS: dict[str, str] = {}
BETAS: dict[str, int] = {}
for _c in _reader["ConfigList"]:
    _pin = _c["AdcChannel"]
    _zone = _c["ChannelName"].removesuffix("-gw-temp").removesuffix("-gw-microvolts")
    if CHANNELS.setdefault(_pin, _zone) != _zone:
        raise SystemExit(f"conflicting channel names on {_pin}")
    if BETAS.setdefault(_pin, _c["ThermistorBeta"]) != _c["ThermistorBeta"]:
        raise SystemExit(f"conflicting betas on {_pin}")

BOARD = {  # echoed into the summary output as provenance
    "layout_path": LAYOUT_PATH,
    "reader_word": f"{_reader['TypeName']}/{_reader['Version']}",
    "decode": _decode_label,
    "layout_sha256": hashlib.sha256(_layout_bytes).hexdigest(),
    "layout_mtime": time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(LAYOUT_PATH))
    ),
    "adc_address": ADDR,
    "adc_reference_volts": V_REF,
    "series_resistance_kohms": R_SERIES_KOHMS,
    "temp_calc_method": _reader["TempCalcMethod"],
    "thermistor_betas": {CHANNELS[p]: b for p, b in BETAS.items()},
}

MUX = {"P0": 0b100, "P1": 0b101, "P2": 0b110, "P3": 0b111}
DR_128SPS, DR_8SPS = 0b100, 0b000

MODES = [
    # (label, dr_bits, conversion_wait_s, poll_period_s, ema_alpha, cycles)
    ("base-128sps-1hz", DR_128SPS, 0.012, 1.0, None, 120),
    ("fast-5hz-ema", DR_128SPS, 0.012, 0.2, 0.2, 600),
    ("slow-8sps-1hz", DR_8SPS, 0.140, 1.0, None, 120),
]
EMA_WARMUP = 25  # discard the EMA's convergence tail from stats

RAW_PATH = "/tmp/ads_noise_raw.jsonl"

bus = None  # smbus2.SMBus(1), opened in main() — import stays lazy so the
# layout-decode logic is importable off-box (no smbus2 on laptops)


def config_word(chan: str, dr_bits: int) -> int:
    return (0x8000 | (MUX[chan] << 12) | (0b001 << 9) | 0x0100
            | (dr_bits << 5) | 0b00011)


def read_channel(chan: str, dr_bits: int, wait_s: float):
    """One gated single-shot conversion -> volts, or an error string."""
    word = config_word(chan, dr_bits)
    try:
        bus.write_i2c_block_data(ADDR, CONFIG_REG, [(word >> 8) & 0xFF, word & 0xFF])
        time.sleep(wait_s)
        for _ in range(2):
            hi, lo = bus.read_i2c_block_data(ADDR, CONFIG_REG, 2)
            if ((hi << 8) | lo) == word:
                break
            time.sleep(wait_s)
        else:
            return None, f"readback mismatch 0x{(hi << 8) | lo:04x}"
        hi, lo = bus.read_i2c_block_data(ADDR, CONVERSION_REG, 2)
        raw = (hi << 8) | lo
        if raw > 0x7FFF:
            raw -= 0x10000
        return raw * FULL_SCALE / 32768, None
    except OSError as e:
        return None, str(e)


def temp_c(volts: float, beta: int) -> float | None:
    if volts <= 0.01 or volts >= V_REF:
        return None
    r = R_SERIES_KOHMS * volts / (V_REF - volts)
    return 1 / ((1 / T0) + (math.log(r / R0_KOHMS) / beta)) - 273


def main() -> None:
    global bus
    import smbus2

    bus = smbus2.SMBus(1)
    results = {}
    raw_f = open(RAW_PATH, "w")
    for label, dr, wait_s, poll_s, alpha, cycles in MODES:
        series: dict[str, list[float]] = {c: [] for c in CHANNELS}
        ema: dict[str, float] = {}
        errors: list[str] = []
        t_start = time.monotonic()
        print(f"\n== {label}: {cycles} cycles at {poll_s}s poll ==", flush=True)
        for i in range(cycles):
            cycle_t0 = time.monotonic()
            for chan in CHANNELS:
                volts, err = read_channel(chan, dr, wait_s)
                rec = {"t": round(time.time(), 3), "mode": label,
                       "chan": CHANNELS[chan]}
                if err is not None:
                    errors.append(f"{chan}: {err}")
                    rec["err"] = err
                    raw_f.write(json.dumps(rec) + "\n")
                    continue
                rec["uv"] = round(volts * 1e6)
                if alpha is not None:
                    prev = ema.get(chan, volts)
                    volts = alpha * volts + (1 - alpha) * prev
                    ema[chan] = volts
                    rec["ema_uv"] = round(volts * 1e6)
                    raw_f.write(json.dumps(rec) + "\n")
                    if i < EMA_WARMUP:
                        continue
                else:
                    raw_f.write(json.dumps(rec) + "\n")
                series[chan].append(volts)
            raw_f.flush()
            time.sleep(max(0.0, poll_s - (time.monotonic() - cycle_t0)))
        elapsed = time.monotonic() - t_start
        mode_out = {"elapsed_s": round(elapsed, 1), "errors": errors}
        print(f"   done in {elapsed:.0f}s, {len(errors)} errors")
        print(f"   {'channel':16} {'n':>4} {'mean uV':>10} {'sd uV':>7} "
              f"{'p2p uV':>7} {'mean C':>7} {'sd C':>6}")
        for chan, name in CHANNELS.items():
            vals = series[chan]
            if len(vals) < 3:
                print(f"   {name:16} insufficient samples")
                continue
            uv = [v * 1e6 for v in vals]
            temps = [t for t in (temp_c(v, BETAS[chan]) for v in vals) if t is not None]
            sd_c = statistics.stdev(temps) if len(temps) > 2 else float("nan")
            mean_c = statistics.mean(temps) if temps else float("nan")
            row = {
                "n": len(vals),
                "mean_uv": round(statistics.mean(uv)),
                "sd_uv": round(statistics.stdev(uv), 1),
                "p2p_uv": round(max(uv) - min(uv)),
                "mean_c": round(mean_c, 2),
                "sd_c": round(sd_c, 4),
            }
            mode_out[name] = row
            print(f"   {name:16} {row['n']:>4} {row['mean_uv']:>10} "
                  f"{row['sd_uv']:>7} {row['p2p_uv']:>7} "
                  f"{row['mean_c']:>7.2f} {row['sd_c']:>6.3f}")
        results[label] = mode_out
    raw_f.close()
    results["board"] = BOARD
    out = "/tmp/ads_noise_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=1)
    print(f"\nresults saved to {out}, raw samples to {RAW_PATH}")


if __name__ == "__main__":
    main()
