# 2026-08-12 · dac-bus-bench

The DAC leg's bench rung (spruce-unlimbo, summer-local-control build step
6's DAC extension): the reworked `I2cDacWriter` on the real honeysuckle
gw108 — every op through `I2cBus` (mux select + Multi-Write + bare EEPROM
read), the boot EEPROM verify against the layout's PowerOn values, and the
heartbeat re-assert. Zero cooling stakes; nothing is wired to the bench Z6
output.

## Why

Two claims want real silicon:

1. **The bus-mediated DAC choreography works on the chip**: TCA9548A mux
   select as `i2c.write.byte`, MCP4728 Multi-Write as `i2c.write.reg`
   (command byte in the register position), the 24-byte bare sequential
   read as `i2c.read.bytes` (i2c_rdwr — `read_i2c_block_data` speaks the
   wrong protocol; the sim can't prove this leg).
2. **The EEPROM verify choreography**: boot #1 should find the bench
   chip's EEPROM differing from the layout's declared PowerOn values
   (A0/B0/C3020/D0, the spruce twin), reprogram via Single Write, re-verify
   (`i2c-dac-eeprom-reprogrammed` glitch); boot #2 should verify silently —
   both verify paths witnessed, plus Multi-Write leaving EEPROM untouched
   between boots.

## Setup (reproducer)

- **Code under test:** gridworks-scada `jm/spruce-unlimbo` `e551c2e1`
  (DAC writer rides I2cBus) — fetch + checkout in the pi's
  `~/gridworks-scada`; driver venv per `tools/mkenv-pi.sh` (standing).
- **Artifact:** `gw.nolan.layout.json` here — the verbatim tlayouts
  honeysuckle artifact (`output/honeysuckle/`, tlayouts `jm/spruce`) plus
  the Dac2 writer component + `gw108-dac2-writer` node appended by
  `append_dac_writer.py` (gwsproto-constructed, wire-identical to what the
  gen emits once `spaceheat.node.gt/304` lands — the published 303 schema
  pins `gw1.actor.class/012`, so the gen cannot emit the node yet).
  md5 `4cc8bc83cb00a2ec192b4c2acc5bffe0`. Ops artifact: the pi's standing
  `gw.house0.operational.params.json` (unchanged).
- **Isolation:** the pi's own mosquitto at `localhost:1883`
  (`d1.bench.honeysuckle` identity; no LAN, no tunnel); no deployed
  service on the pi.
- **Runbook** (backup → run twice → restore standing state):

      scp gw.nolan.layout.json honeysuckle:gw.nolan.layout.dac-bench.json
      ssh honeysuckle 'cd ~/gridworks-scada && git fetch && git checkout jm/spruce-unlimbo && git pull'
      ssh honeysuckle 'cp ~/.config/gridworks/scada/hardware-layout.json ~/hardware-layout.standing.json && cp ~/gw.nolan.layout.dac-bench.json ~/.config/gridworks/scada/hardware-layout.json'
      # boot 1 — mismatch → reprogram → re-verify expected
      ssh honeysuckle 'cd ~/gridworks-scada/gw_spaceheat && timeout 150 venv/bin/python cli.py run > /tmp/dac-bench-boot1.log 2>&1; true'
      scp honeysuckle:/tmp/dac-bench-boot1.log boot1-<DATE>.log
      # boot 2 — clean verify expected
      ssh honeysuckle 'cd ~/gridworks-scada/gw_spaceheat && timeout 150 venv/bin/python cli.py run > /tmp/dac-bench-boot2.log 2>&1; true'
      scp honeysuckle:/tmp/dac-bench-boot2.log boot2-<DATE>.log
      ssh honeysuckle 'cp ~/hardware-layout.standing.json ~/.config/gridworks/scada/hardware-layout.json'

## Found

**Both claims PASS; one chip-timing finding, fixed same day.**

- **Boot #1 (13:27–13:29 ET, `boot1-2026-08-12.log`):** the full
  choreography ran through the bus — mux select, Multi-Write assertion of
  all four targets, bare 24-byte EEPROM reads — with ZERO
  `i2c-dac-write-failed` glitches across the run. The EEPROM verify found
  the bench chip's values differing from the layout's (as designed) and
  converged them — but over THREE heartbeat passes
  (`i2c-dac-eeprom-verify-failed` 13:27:02 and 13:28:02, clean 13:29:02)
  instead of one reprogram → re-verify cycle.
- **The finding:** the MCP4728 is busy ~25–50 ms per EEPROM write and
  reads meanwhile return the OLD EEPROM data; the verify's immediate
  re-read saw stale values, so each pass's reprogram looked failed until
  the next heartbeat. The containment worked exactly as designed (retry
  until verified, throttled warnings), but the correct behavior is a
  settle wait per Single Write.
- **Boot #2 (13:30, `boot2-2026-08-12.log`):** EEPROM verified clean on
  the FIRST pass — proving the verify's clean path AND that Multi-Write
  left EEPROM untouched across a full boot of assertions.
- **The fix (same day, follows this record):** `EEPROM_WRITE_TIME_S` in
  `drivers/mcp4728.py`; the verify sleeps it after each Single Write.
  `SimMcp4728` now models the busy window (reads mid-cycle return old
  data), which turns the existing verify test into the regression net —
  the sim could never have caught this before the bench run taught it the
  shape. Caveat: the mismatch path *under the fix* is witnessed in sim
  only (the bench EEPROM now matches the layout, so the mismatch branch
  no longer triggers there); spruce's chip also matches (hack
  provisioning), so the next natural hardware witness is a fresh board.
- Standing state restored after boot #2 (gen artifact back in place,
  md5 `af75763f…` — the tlayouts `output/honeysuckle/` file).

## Verified (scoped claims)

- Mux select (`i2c.write.byte`), Multi-Write value assertion
  (`i2c.write.reg`, command byte in the register position), and the bare
  24-byte sequential read (`i2c.read.bytes` via i2c_rdwr) all work on the
  real TCA9548A + MCP4728 through the serialized bus actor.
- Boot EEPROM verify: mismatch → reprogram → converge (boot #1),
  clean-verify single pass (boot #2).
- Routine assertion provably EEPROM-free: boot #2's clean verify after
  boot #1's ~2 minutes of Multi-Write heartbeat assertions.
