"""Spike client: connect to the spike broker with the test client cert and
a fis.connect.claims-shaped SASL response, via a custom pika credentials
class — the shape gwbase's real class will take. Run:

    uv run --with pika client_test.py

The claims JSON is hand-built: the fis.connect.claims word is not authored
in the sema registry yet, and the plugin is payload-opaque, so any bytes
prove the path. gwbase will construct the real word via its snapshot."""

import json
import ssl

import pika

CLAIMS = {
    "Alias": "hw1.isone.weather",
    "InstanceId": "0f6a2f7e-6f2d-4a8b-9c3e-2d1b4a5c6e7f",
    "Run": "hw1__1",
    "GNodeClass": "WeatherForecastService",
    "TypeName": "fis.connect.claims",
    "Version": "000",
}


class GridworksCredentials:
    """Pika credentials for the GRIDWORKS SASL mechanism: identity rides
    the client cert (TLS layer); the SASL response carries the claims."""

    TYPE = "GRIDWORKS"

    def __init__(self, claims: dict):
        self._claims = claims

    def response_for(self, start):
        if self.TYPE.encode() not in start.mechanisms.split():
            return None, None
        return self.TYPE, json.dumps(self._claims).encode()

    def erase_credentials(self) -> None:
        pass


# pika validates the credentials object against this module-level list —
# registering the class here is the supported extension point (gwbase's
# real class does the same at import time).
pika.credentials.VALID_TYPES.append(GridworksCredentials)


def main() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations("certs/out/ca.pem")
    ctx.load_cert_chain("certs/out/client.pem", "certs/out/client.key")
    params = pika.ConnectionParameters(
        host="localhost",
        port=5671,
        virtual_host="/",
        ssl_options=pika.SSLOptions(ctx, server_hostname="localhost"),
        credentials=GridworksCredentials(CLAIMS),
    )
    conn = pika.BlockingConnection(params)
    print("CONNECTED — now check: docker compose logs stub-fis")
    conn.close()


if __name__ == "__main__":
    main()
