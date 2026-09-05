"""The reconnect storm: N distinct service principals connect at once through
the gate, each a never-seen instance (a supersession with nothing to kill).
Measures the client-side connect time; the pass bar is every connect allowed
and none near the broker's 10 s handshake_timeout.

    uv run --project ../../gridworks-fleet-index-service --with pika --with ../../gridworks-base storm.py
"""

import argparse
import json
import os
import signal
import ssl
import statistics
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import psycopg
import pika
import pika.exceptions
from gwbase.credentials import GridworksClaimsCredentials
from gwbase.sema.types import FisConnectClaims

HERE = Path(__file__).parent
FIS_DIR = (HERE / "../../gridworks-fleet-index-service").resolve()
CERTS = HERE / "certs/out"
IDS = dict(line.split("=", 1) for line in (CERTS / "ids.env").read_text().splitlines() if "=" in line)
FIS_ENV = {
    "FIS_RABBIT_MGMT_URL": "http://localhost:15673",
    "FIS_RABBIT_MGMT_USER": "smqPublic",
    "FIS_RABBIT_MGMT_PASSWORD": "smqPublic",
    "FIS_GNR_URL": "http://localhost:8000",
}


def connect_one(name: str, out: dict[str, tuple[str, float]], go: threading.Event) -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(str(CERTS / "ca.pem"))
    ctx.load_cert_chain(str(CERTS / f"{name}.pem"), str(CERTS / f"{name}.key"))
    params = pika.ConnectionParameters(
        host="localhost",
        port=5671,
        virtual_host="d1__1",
        ssl_options=pika.SSLOptions(ctx, server_hostname="localhost"),
        credentials=GridworksClaimsCredentials(
            FisConnectClaims(alias=f"d1.storm.{name}", instance_id=str(uuid.uuid4()), run="d1__1")
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
    names = sorted(n for n in IDS if n.startswith("service"))

    with psycopg.connect("postgresql://fis:fispass@localhost:5437/fis", autocommit=True) as _c:
        _c.execute("truncate leases, auth_events, g_nodes")
    fis = subprocess.Popen(
        ["uv", "run", "--project", str(FIS_DIR), "fis", "api"],
        cwd=HERE, env={**os.environ, **FIS_ENV},
        stdout=open(run_dir / "fis-storm.log", "a"), stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        for _ in range(60):
            try:
                if httpx.get("http://127.0.0.1:8080/ping", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        out: dict[str, tuple[str, float]] = {}
        go = threading.Event()
        threads = [threading.Thread(target=connect_one, args=(n, out, go)) for n in names]
        for t in threads:
            t.start()
        time.sleep(0.5)
        t_storm = time.perf_counter()
        go.set()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t_storm
    finally:
        os.killpg(os.getpgid(fis.pid), signal.SIGTERM)
        fis.wait(timeout=15)

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
