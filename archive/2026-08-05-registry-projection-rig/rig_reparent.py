"""EDD rig leg 3: publish a g.node.reparent.cmd as the keene MarketMaker
against the LIVE rig (running gnr write loop, gjk, ear), and wait for the
registry's forest broadcast to come back on the audience-known channel.

Run from grid-node-registry root:
    uv run python <scratchpad>/rig_reparent.py
"""

import json
import time
import uuid

from pydantic import SecretStr
from sqlalchemy import text

from gwbase.config import ServiceSettings
from gwbase.config.rabbit_settings import RabbitBrokerClient
from gwbase.orchestrator import Orchestrator
from gwbase.transport_encoding import TransportClass

from gnr.db.session import SessionLocal
from gnr.dev_universe import DEV_POSITION
from gnr.sema.codec import SemaCodec
from gnr.sema.enums import BaseGNodeClass, GNodeStatus
from gnr.sema.types import GNodeForest, GNodeGt, GNodeReparentCmd

KEENE = "d1.isone.me.versant.keene"
REGISTRY = "d1.gnr"
RABBIT_URL = "amqp://smqPublic:smqPublic@localhost:5672/d1__1"


class MM(Orchestrator):
    def __init__(self, settings: ServiceSettings) -> None:
        super().__init__(
            settings=settings,
            transport_class=TransportClass.MarketMaker,
            my_super_alias="d1.super1",
            my_time_coordinator_alias="d1.time",
        )
        self.broadcasts: list[bytes] = []

    def local_rabbit_startup(self) -> None:
        self.subscribe_broadcast(
            from_alias=REGISTRY,
            from_class=TransportClass.GridNodeRegistry,
            type_name="g.node.forest",
            radio_channel=KEENE,
        )

    def process_message(self, *, envelope, body: bytes) -> None:
        if envelope.type_name == "g.node.forest":
            self.broadcasts.append(body)


def wait_for(predicate, timeout_s: float, message: str) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for: {message}")


def main() -> None:
    with SessionLocal() as s:
        beech_id = s.execute(
            text("select id from g_nodes where alias = :a"), {"a": f"{KEENE}.beech"}
        ).scalar()
    print(f"beech ltn id: {beech_id}")

    mm = MM(
        ServiceSettings(
            service_alias=KEENE,
            rabbit=RabbitBrokerClient(url=SecretStr(RABBIT_URL)),
        )
    )
    mm.start()
    try:
        wait_for(lambda: mm._consuming, 15, "marketmaker consuming")
        new_cn = GNodeGt(
            g_node_id=str(uuid.uuid4()),
            alias=f"{KEENE}.sub",
            base_class=BaseGNodeClass.ConnectivityNode,
            g_node_class="ConnectivityNode",
            status=GNodeStatus.Active,
            position_point_id=DEV_POSITION.id,
            display_name="Rig Sub CN",
        )
        cmd = GNodeReparentCmd(
            new_node=new_cn, moved_child_g_node_ids=[str(beech_id)]
        )
        mm.send(
            envelope=mm.direct_envelope(
                type_name=cmd.type_name,
                to_class=TransportClass.GridNodeRegistry,
                to_alias=REGISTRY,
            ),
            body=cmd.to_bytes(),
        )
        print("reparent cmd published as keene MarketMaker")
        wait_for(lambda: len(mm.broadcasts) > 0, 30, "forest broadcast")
        forest = SemaCodec().from_dict(json.loads(mm.broadcasts[0]))
        assert isinstance(forest, GNodeForest)
        print(
            f"broadcast received: Version={forest.version} "
            f"SendTimeMs={forest.send_time_ms} "
            f"nodes={len(forest.nodes)}"
        )
        print("aliases:", sorted(g.alias for g in forest.nodes))
    finally:
        mm.stop()


if __name__ == "__main__":
    main()
