"""Dev-machine side of the DAC output bench rung: drive honeysuckle's
secondary-010v through the scada's admin link and print what comes back.

Runs here, not on the pi, through an ssh tunnel to the pi's mosquitto
(`ssh -f -N -L 1884:localhost:1884 honeysuckle` after the pi's broker gains a
1884 listener; see README). Uses the gridworks-admin client the way the admin
TUI does, so the message shape is the real one: AdminAnalogDispatch wrapping
AnalogDispatch(ToHandle="admin.secondary-010v", Value=<volts x 10>).

    HONEYSUCKLE_MQTT_PASS=... gw_spaceheat/venv/bin/python bench_dispatch.py 55
    HONEYSUCKLE_MQTT_PASS=... gw_spaceheat/venv/bin/python bench_dispatch.py release
"""

import asyncio
import logging
import os
import sys

from gwadmin.config import AdminConfig, AdminMQTTClient, CurrentAdminConfig, ScadaConfig
from gwproactor.config.mqtt import TLSInfo
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwadmin.watch.clients.dac_client import DACClientCallbacks, DACWatchClient

SCADA_LONG_NAME = "d1.bench.honeysuckle.scada"
DAC_ROW = "secondary"  # the client appends "-010v"
TUNNEL_PORT = 1884
ADMIN_TIMEOUT_S = 120
SETTLE_S = 8


def admin_config() -> CurrentAdminConfig:
    password = os.environ.get("HONEYSUCKLE_MQTT_PASS")
    if not password:
        raise SystemExit("set HONEYSUCKLE_MQTT_PASS (the pi's SCADA_LOCAL_MQTT__PASSWORD)")
    return CurrentAdminConfig(
        config=AdminConfig(
            scadas={
                "honeysuckle": ScadaConfig(
                    long_name=SCADA_LONG_NAME,
                    mqtt=AdminMQTTClient(
                        host="localhost", port=TUNNEL_PORT,
                        username="bench", password=password,
                        tls=TLSInfo(use_tls=False),
                    ),
                )
            },
            default_scada="honeysuckle",
        ),
        curr_scada="honeysuckle",
    )


async def main(action: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    dac_client = DACWatchClient(
        DACClientCallbacks(
            dac_state_change_callback=lambda changes: print("DAC state:", changes),
            dac_config_change_callback=lambda changes: print("DAC config:", changes),
            mqtt_state_change_callback=lambda old, new: print(f"mqtt {old} -> {new}"),
        )
    )
    client = AdminClient(admin_config(), AdminClientCallbacks(), [dac_client])
    client.start()
    await asyncio.sleep(SETTLE_S)  # connect + ScadaControlCapabilities round trip
    if action == "release":
        dac_client.send_release_control()
    else:
        value = int(action)
        if not 0 <= value <= 100:
            raise SystemExit("value is volts x 10, 0..100")
        dac_client.set_dac(DAC_ROW, value, timeout_seconds=ADMIN_TIMEOUT_S)
        print(f"sent secondary-010v <- {value} (volts x 10); watching {SETTLE_S}s")
    await asyncio.sleep(SETTLE_S)
    client.stop()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
