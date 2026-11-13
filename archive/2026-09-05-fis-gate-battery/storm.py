"""The reconnect storm: N distinct service principals connect at once through
the gate, each a never-seen instance (a supersession with nothing to kill).
Measures the client-side connect time; the pass bar is every connect allowed
and none near the broker's 10 s handshake_timeout.

    uv run --project ../../gridworks-fleet-index-service --with pika --with ../../gridworks-base storm.py

The rig (broker, identities, the FIS lever) comes from the environment, as
for battery.py: the local harness by default, `remote.env` for a box.
"""

import argparse
import json
import ssl
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path

import pika
import pika.exceptions
from gwbase.credentials import GridworksClaimsCredentials
from gwbase.sema.types import FisConnectClaims

from rig import Rig, rig_from_env

HERE = Path(__file__).parent


def connect_one(rig: Rig, name: str, out: dict[str, tuple[str, float]], go: threading.Event) -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(rig.ca)
    ctx.load_cert_chain(*rig.cert(name))
    params = pika.ConnectionParameters(
        host=rig.broker_host,
        port=rig.amqps_port,
        virtual_host=rig.run,
        ssl_options=pika.SSLOptions(ctx, server_hostname=rig.broker_host),
        credentials=GridworksClaimsCredentials(
            FisConnectClaims(alias=rig.alias(f"storm.{name}"), instance_id=str(uuid.uuid4()), run=rig.run)
        ),
        connection_attempts=1,
        socket_timeout=20,
    )
    go.wait()
    t0 = time.perf_counter()
    try:
        conn = pika.BlockingConnection(params)
        out[name] = ("allow", time.perf_counter() - t0)
        time.sleep(1.0)  # hold, so the storm overlaps rather than trickles
        conn.close()
    except Exception as e:  # noqa: BLE001 -- every failure is a data point
        out[name] = (f"{type(e).__name__}", time.perf_counter() - t0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=str(HERE / "runs" / time.strftime("%Y%m%dT%H%M", time.gmtime())))
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rig = rig_from_env(run_dir, fis_log_name="fis-storm.log")
    names = sorted(n for n in rig.ids if n.startswith("service"))

    rig.fis_stop()
    rig.reset_lease_state()
    rig.fis_start()
    try:
        out: dict[str, tuple[str, float]] = {}
        go = threading.Event()
        threads = [threading.Thread(target=connect_one, args=(rig, n, out, go)) for n in names]
        for t in threads:
            t.start()
        time.sleep(0.5)
        t_storm = time.perf_counter()
        go.set()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t_storm
    finally:
        rig.close()

    times = sorted(dt for _, dt in out.values())
    allowed = sum(1 for tag, _ in out.values() if tag == "allow")
    summary = {
        "n": len(names),
        "allowed": allowed,
        "wall_s": round(wall, 2),
        "connect_s": {
            "p50": round(statistics.median(times), 3),
            "p95": round(times[int(0.95 * (len(times) - 1))], 3),
            "max": round(times[-1], 3),
        },
        "failures": {n: tag for n, (tag, _) in out.items() if tag != "allow"},
    }
    print(json.dumps(summary, indent=1))
    (run_dir / "storm.json").write_text(json.dumps(summary, indent=1))
    ok = allowed == len(names) and times[-1] < 5.0
    print(f"{'PASS' if ok else 'FAIL'}  storm: {allowed}/{len(names)} allowed, max connect {times[-1]:.2f}s (bar: all allowed, max < 5s of the 10s handshake budget)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
