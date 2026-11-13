"""Drive a real cert + real claims through the broker into the stub FIS.

This uses gwbase's own credentials class and the fis.connect.claims word from
its vendored snapshot — not a local imitation of them — so what the stub
records is what a production actor would actually send. Run:

    uv run --with pika --with ../../gridworks-base client_test.py
"""

import ssl

from gwbase.credentials import GridworksClaimsCredentials
from gwbase.sema.types import FisConnectClaims

import pika

CLAIMS = FisConnectClaims(
    alias="d1.isone.weather",
    instance_id="0f6a2f7e-6f2d-4a8b-9c3e-2d1b4a5c6e7f",
    run="d1__1",
    g_node_class="WeatherForecastService",
)


def main() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations("certs/out/ca.pem")
    ctx.load_cert_chain("certs/out/client.pem", "certs/out/client.key")
    params = pika.ConnectionParameters(
        host="localhost",
        port=5671,
        # The vhost names the run being joined; the claims say which run this
        # process believes it is joining, and FIS cross-checks the two.
        virtual_host="d1__1",
        ssl_options=pika.SSLOptions(ctx, server_hostname="localhost"),
        credentials=GridworksClaimsCredentials(CLAIMS),
    )
    conn = pika.BlockingConnection(params)
    print("CONNECTED — now check: docker compose logs stub-fis")
    conn.close()


if __name__ == "__main__":
    main()
