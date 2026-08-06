# Pico link-type census — wired (Wiznet) vs wifi (Pico W), fleet-wide

Genre: observational analysis. Run 2026-08-05; reproducer
`pico_link_census.py` (read-only; ssh to the house pis, classify neighbor
MACs by manufacturer OUI).

## CORRECTED finding: OUI cannot discriminate link type

First run reported "0 Wiznet MACs → every pico is wifi." **That
conclusion was WRONG** — wired Wiznet tank picos are known to exist (at
beech at least). The mechanism of the error, from the firmware
(`gridworks-pico/tank_module/tank_module_3_main.py`): link type comes
from each pico's on-flash `comms_config.json` (`WifiOrEthernet`), and
the ethernet path brings up MicroPython's `network.WIZNET5K()` with **no
explicit MAC** — the driver derives a default that does not carry
WIZnet's OUI, so wired and wifi picos are indistinguishable by MAC
prefix. The census's raw observation (36 pico-class MACs, all
RPi-family prefixes) stands as a MAC fact but supports no link-type
conclusion.

Picos do NOT self-report link type in their posts, and the layouts do
not carry it. **Ground truth found (2026-08-05): the hand-maintained
Device Registry sheet** (pico model column — "wiznet Eth pico" vs "wifi
pico"; per-house attribution partly stale, but the model↔HwUid map is
trusted):

- **Wired (Wiznet) tank picos: maple, oak, fir, beech** (4 each).
- **Wifi: elm's tanks, all flow/BTU picos fleet-wide, and all of
  spruce's** (hand-made older units, redeployed from other houses —
  the registry lists them under their previous homes; secondary-btu's
  pico_1c3c31 is unlisted).

Cross-checks against the reliability data:

- fir's zombie pico (tank2, pico_8e5e21) is WIRED — its brief flatlines
  are power/board, not wifi.
- beech's hourly disturbance zombies its WIRED tank picos too — the
  hourly event is common infrastructure (router/switch/pi/scada), not
  wifi.
- elm's all-wifi tanks ran 56 days gapless — wifi-clean is achievable.

Long-term fix stands: firmware self-report (`WifiOrEthernet` + MAC in
the params post) → scada → layout carriage, replacing the hand sheet.

## What the 56-day gap data still says (unchanged)

fir 0 gaps · oak 0 gaps · maple 1 gap: all three candidate houses are
effectively flawless — but WITHOUT the link-type census the router
comparison stays confounded (a flawless house may just be heavily
wired). spruce's trouble remains device-scoped (2 of 9 picos); elm's
blemish was one ~33 h whole-house outage.

## Raw census (2026-08-05)

Per-house MAC/IP tables: re-run `pico_link_census.py`. HwUid is the
RP2040 flash serial (`machine.unique_id()[-6:]`), not MAC-derived.
