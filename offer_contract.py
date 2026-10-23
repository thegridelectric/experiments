#!/usr/bin/env python
"""Offer a window scada a slow dispatch contract, as its LTN, right now.

    ../gridworks-scada/gw_spaceheat/venv/bin/python offer_contract.py <target> [--watts N] [--minutes M]

<target> is dev, spruce, beech or maple: the layout pair a laptop LTN
loads for that target (the laptop's ~/.config/gridworks/ltn/ pair in dev,
the tlayouts gen output for a house), so the offer names the target's
scada and comes from the alias the scada expects upstream.

The LTN offers only in the ten seconds after the top of the hour. This
script publishes one Created slow.contract.heartbeat on the laptop's
gw-dev-rabbit, on the LTN's own topic, so a refusal or an acceptance can
be read in the scada log and the broker capture within a minute. The
contract starts at the next five-minute slot. The laptop LTN, if it is
running, did not make this offer and ignores the scada's answer to it.

This is a forgery of the LTN, and it works because nothing yet signs the
right to dispatch: the signed TaTradingRights validation is what will
make this impossible on a real bus. Dev broker only; the window scripts
never put it on the prod broker.
"""

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

import dotenv
import paho.mqtt.client as mqtt
from gwproto import Message
from gwsproto.enums import SlowDispatchContractStatus
from gwsproto.named_types import SlowContractHeartbeat, SlowDispatchContract
from gwsproto.names.core.node_names import CoreNodeNames

HERE = Path(__file__).resolve().parent
SCADA = HERE.parent / "gridworks-scada"
TLAYOUTS = HERE.parent / "tlayouts" / "output"
sys.path.insert(0, str(SCADA / "gw_spaceheat"))

from actors.ltn.config import LtnSettings  # noqa: E402
from sema_to_dc import load_layout  # noqa: E402

PAIRS: dict[str, tuple[Path, Path]] = {
    "dev": (
        Path.home() / ".config/gridworks/ltn/hardware-layout.json",
        Path.home() / ".config/gridworks/ltn/operational-params.json",
    ),
    "spruce": (
        TLAYOUTS / "spruce/gw.nolan.layout.json",
        TLAYOUTS / "spruce/gw.nolan.operational.params.json",
    ),
    "beech": (
        TLAYOUTS / "beech/hardware-layout.generated.json",
        TLAYOUTS / "beech/operational-params.generated.json",
    ),
    "maple": (
        TLAYOUTS / "maple/hardware-layout.generated.json",
        TLAYOUTS / "maple/operational-params.generated.json",
    ),
}


def main() -> None:
    p = argparse.ArgumentParser(description="Offer a window scada a slow dispatch contract, as its LTN, right now.")
    p.add_argument("target", choices=sorted(PAIRS))
    p.add_argument("--watts", type=int, default=1000, help="AvgPowerWatts (default 1000)")
    p.add_argument("--minutes", type=int, default=60, help="DurationMinutes (default 60)")
    a = p.parse_args()

    layout_path, ops_path = PAIRS[a.target]
    layout = load_layout(layout_path, ops_path)
    ltn_alias = layout.ltn_g_node_alias
    scada_alias = layout.scada_g_node_alias

    dotenv.load_dotenv(SCADA / ".env")
    settings = LtnSettings()
    broker = settings.scada_mqtt
    if broker.host not in ("localhost", "127.0.0.1"):
        sys.exit(f"refusing: LTN_SCADA_MQTT__HOST is {broker.host}; this script offers on the dev broker only")

    contract = SlowDispatchContract(
        ScadaAlias=scada_alias,
        StartS=(int(time.time()) // 300) * 300 + 300,
        DurationMinutes=a.minutes,
        AvgPowerWatts=a.watts,
        OilBoilerOn=False,
        ContractId=str(uuid.uuid4()),
    )
    hb = SlowContractHeartbeat(
        FromNode=CoreNodeNames.ltn,
        Contract=contract,
        Status=SlowDispatchContractStatus.Created,
        MessageCreatedMs=int(time.time() * 1000),
        MyDigit=7,
        YourLastDigit=None,
    )
    msg = Message(Src=ltn_alias, Dst=CoreNodeNames.primary_scada, Payload=hb)
    topic = msg.mqtt_topic()
    body = msg.model_dump_json(exclude_none=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"offer-contract-{os.getpid()}")
    client.username_pw_set(broker.username, broker.password.get_secret_value())
    client.connect(broker.host, broker.port, keepalive=10)
    info = client.publish(topic, body, qos=1)
    info.wait_for_publish(timeout=5)
    client.disconnect()

    print(f"offered {contract.ContractId}")
    print(f"  from {ltn_alias} to {scada_alias} on {topic}")
    print(f"  StartS {contract.StartS} ({time.strftime('%H:%M:%S', time.localtime(contract.StartS))}), "
          f"{a.minutes} min, {a.watts} W")
    print(f"  answer: grep -i '{contract.ContractId}\\|Refusing contract\\|rejection' the window scada log")


if __name__ == "__main__":
    main()
