"""The end-state witness: a real ActorBase actor, configured only through
settings, connects through the GRIDWORKS mechanism to the stub FIS.

Nothing here builds claims or credentials by hand — the actor derives the
claims from its own alias/instance/run and the tls block switches the
connect path. Run:

    uv run --with pika --with ../../gridworks-base actor_test.py
"""

import pika
from pydantic import SecretStr

from gwbase.actor_base import ActorBase, RoutingEnvelope
from gwbase.config import ServiceSettings
from gwbase.config.rabbit_settings import RabbitBrokerClient, RabbitTls


class SpikeTap(ActorBase):
    def dispatch_message(self, *, envelope: RoutingEnvelope, body: bytes) -> None:
        raise NotImplementedError  # connect-time witness only


def main() -> None:
    settings = ServiceSettings(
        service_alias="d1.spike.tap",
        rabbit=RabbitBrokerClient(
            url=SecretStr("amqps://localhost:5671/d1__1"),
            tls=RabbitTls(
                ca_cert_path="certs/out/ca.pem",
                cert_path="certs/out/client.pem",
                private_key_path="certs/out/client.key",
            ),
        ),
    )
    actor = SpikeTap(settings=settings)
    conn = pika.BlockingConnection(actor._connection_parameters())
    print(
        f"CONNECTED as {actor.alias} (instance {actor.instance_id}, run "
        f"{settings.rabbit.run}) — now check: docker compose logs stub-fis"
    )
    conn.close()


if __name__ == "__main__":
    main()
