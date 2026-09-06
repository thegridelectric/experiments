"""The rig the battery and the storm run against, read from the environment.

Local (the default): the harness broker on this machine and a FIS process
the battery owns. Remote (`BATTERY_RIG=remote`, values in `remote.env`): a
broker box with FIS under systemd, driven over ssh — FIS starts and stops
through `systemctl`, the management-API-down leg runs an ad-hoc `fis api`
with a wrong password, the broker's connection list comes from
`rabbitmqctl` in the box's container, and the FIS database and `/ping`
ride an ssh tunnel. The cases themselves are the same code either way.
"""

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import ClassVar

import httpx
import psycopg

HERE = Path(__file__).parent
FIS_DIR = (HERE / "../../gridworks-fleet-index-service").resolve()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Rig:
    """What every leg needs: where the broker is, who the identities are,
    and the levers on FIS and the broker. Subclasses supply the levers."""

    def __init__(self, run_dir: Path, fis_log_name: str = "fis.log") -> None:
        self.run_dir = run_dir
        self.fis_log_path = run_dir / fis_log_name
        self.broker_host = _env("BATTERY_BROKER_HOST", "localhost")
        self.amqps_port = int(_env("BATTERY_AMQPS_PORT", "5671"))
        self.mqtts_port = int(_env("BATTERY_MQTTS_PORT", "8883"))
        self.run = _env("BATTERY_RUN", "d1__1")
        self.universe = self.run.split("__", 1)[0]
        # a run in the same universe that is not this vhost; one outside it
        self.other_run = _env("BATTERY_OTHER_RUN", "d1__2")
        self.foreign_run = _env("BATTERY_FOREIGN_RUN", "hw1__1")
        self.weather_alias = _env("BATTERY_WEATHER_ALIAS", "d1.isone.me.weather")
        self.weather_class = "WeatherForecastService"
        self.scada_alias = _env("BATTERY_SCADA_ALIAS", "d1.isone.me.versant.keene.sub.beech.scada")
        self.ltn_alias = _env("BATTERY_LTN_ALIAS", "d1.isone.me.versant.keene.sub.beech")
        # a registry alias that is not the identity's own
        self.stale_alias = _env("BATTERY_STALE_ALIAS", "d1.isone.me.price")
        self.certs = HERE / _env("BATTERY_CERTS_DIR", "certs/out")
        self.ca = str(self.certs / "ca.pem")
        self.ids = dict(
            line.split("=", 1)
            for line in (self.certs / "ids.env").read_text().splitlines()
            if "=" in line
        )

    def alias(self, tail: str) -> str:
        """An alias in this rig's universe (`battery.tap` → `d1.battery.tap`)."""
        return f"{self.universe}.{tail}"

    def cert(self, name: str) -> tuple[str, str]:
        return str(self.certs / f"{name}.pem"), str(self.certs / f"{name}.key")

    @property
    def db_url(self) -> str:
        raise NotImplementedError

    @property
    def fis_url(self) -> str:
        raise NotImplementedError

    def fis_start(self, **overrides: str) -> None:
        raise NotImplementedError

    def fis_stop(self) -> None:
        raise NotImplementedError

    def live_connections(self, principal: str) -> set[str]:
        """The broker's own list of open connections for a principal
        (server-side truth, not the management database, which lags). Names
        are the broker's `host:port -> host:port` connection ids."""
        raise NotImplementedError

    def principal_status(self, principal: str, verb: str) -> None:
        """`fis principal suspend|activate` on the FIS that gates the rig."""
        raise NotImplementedError

    def close(self) -> None:
        """End of run: FIS back as found, evidence collected."""
        self.fis_stop()

    # shared pieces

    def reset_lease_state(self) -> None:
        """Clear leases, auth events and the registry mirror before a run, so
        a verdict is decided by this run's connects and not by a prior one's
        rows. Principals stay (their ids are the cert CNs); the mirror
        re-seeds from the registry on FIS boot."""
        with psycopg.connect(self.db_url, autocommit=True) as conn:
            conn.execute("truncate leases, auth_events, g_nodes")

    def wait_fis(self, up: bool, within_s: float) -> None:
        deadline = time.perf_counter() + within_s
        while time.perf_counter() < deadline:
            try:
                answering = httpx.get(f"{self.fis_url}/ping", timeout=1).status_code == 200
            except httpx.HTTPError:
                answering = False
            if answering == up:
                return
            time.sleep(0.5)
        state = "come up" if up else "go down"
        raise RuntimeError(f"FIS did not {state}; see {self.fis_log_path}")

    @staticmethod
    def connection_names(rabbitmqctl_out: str, principal: str) -> set[str]:
        return {
            line.split("\t", 1)[1]
            for line in rabbitmqctl_out.splitlines()
            if line.startswith(principal + "\t")
        }


class LocalRig(Rig):
    """The harness broker (`fis-gate-broker`) and a FIS process this machine
    owns, logging to the run folder."""

    BROKER = "fis-gate-broker"
    FIS_ENV: ClassVar[dict[str, str]] = {
        "FIS_RABBIT_MGMT_URL": "http://localhost:15673",
        "FIS_RABBIT_MGMT_USER": "smqPublic",
        "FIS_RABBIT_MGMT_PASSWORD": "smqPublic",
        "FIS_GNR_URL": "http://localhost:8000",
    }

    def __init__(self, run_dir: Path, fis_log_name: str = "fis.log") -> None:
        super().__init__(run_dir, fis_log_name)
        self.proc: subprocess.Popen | None = None

    @property
    def db_url(self) -> str:
        return "postgresql://fis:fispass@localhost:5437/fis"

    @property
    def fis_url(self) -> str:
        return "http://127.0.0.1:8080"

    def fis_start(self, **overrides: str) -> None:
        env = {**os.environ, **self.FIS_ENV, **overrides}
        self.proc = subprocess.Popen(
            ["uv", "run", "--project", str(FIS_DIR), "fis", "api"],
            cwd=HERE,
            env=env,
            stdout=open(self.fis_log_path, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.wait_fis(up=True, within_s=30)

    def fis_stop(self) -> None:
        if self.proc is None:
            return
        os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        self.proc.wait(timeout=15)
        self.proc = None
        self.wait_fis(up=False, within_s=10)  # the socket must be free before a restart

    def live_connections(self, principal: str) -> set[str]:
        out = subprocess.run(
            ["docker", "exec", "-u", "rabbitmq", self.BROKER, "rabbitmqctl", "-q",
             "list_connections", "user", "name"],
            capture_output=True, text=True, check=False,
        ).stdout
        return self.connection_names(out, principal)

    def principal_status(self, principal: str, verb: str) -> None:
        subprocess.run(
            ["uv", "run", "--project", str(FIS_DIR), "fis", "principal", verb, principal],
            check=True, capture_output=True, cwd=HERE,
        )


class RemoteRig(Rig):
    """A broker box: FIS under `fis-api.service` in the `fis` login, the
    broker in a container under the `broker` login. Every lever is an ssh
    command (multiplexed over one master connection); the FIS database and
    `/ping` are reached through an ssh tunnel this object holds open."""

    DB_TUNNEL_PORT = 15437
    FIS_TUNNEL_PORT = 18080
    ADHOC_LOG = "/tmp/fis-battery-adhoc.log"

    def __init__(self, run_dir: Path, fis_log_name: str = "fis.log") -> None:
        super().__init__(run_dir, fis_log_name)
        self.fis_login = os.environ["BATTERY_FIS_LOGIN"]
        self.fis_checkout = os.environ["BATTERY_FIS_CHECKOUT"]
        self.broker_login = os.environ["BATTERY_BROKER_LOGIN"]
        self.container = os.environ["BATTERY_BROKER_CONTAINER"]
        self.tunnel = subprocess.Popen(
            ["ssh", *self.mux, "-N",
             "-L", f"{self.DB_TUNNEL_PORT}:127.0.0.1:5437",
             "-L", f"{self.FIS_TUNNEL_PORT}:127.0.0.1:8080",
             self.fis_login],
            start_new_session=True,
        )
        # the journal window opens on the box's clock, not this machine's
        self.started_utc = self.ssh_fis("date -u '+%Y-%m-%d %H:%M:%S'").strip()
        # the box's own database credential, never copied off the box
        line = self.ssh_fis(f"grep '^FIS_DB_URL=' {self.fis_checkout}/.env")
        box_url = line.split("=", 1)[1].strip()
        self.remote_db_url = (
            box_url.replace("postgresql+psycopg://", "postgresql://")
            .replace("@localhost:5437/", f"@127.0.0.1:{self.DB_TUNNEL_PORT}/")
        )
        self.wait_tunnel()

    @property
    def mux(self) -> list[str]:
        return ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/cm-%C",
                "-o", "ControlPersist=120", "-o", "BatchMode=yes"]

    def ssh(self, login: str, cmd: str) -> str:
        return subprocess.run(
            ["ssh", *self.mux, login, cmd], check=True, capture_output=True, text=True,
        ).stdout

    def ssh_fis(self, cmd: str) -> str:
        return self.ssh(self.fis_login, cmd)

    def wait_tunnel(self) -> None:
        for _ in range(40):
            try:
                with psycopg.connect(self.remote_db_url, connect_timeout=2):
                    return
            except psycopg.OperationalError:
                time.sleep(0.5)
        raise RuntimeError("ssh tunnel to the box's FIS database did not open")

    @property
    def db_url(self) -> str:
        return self.remote_db_url

    @property
    def fis_url(self) -> str:
        return f"http://127.0.0.1:{self.FIS_TUNNEL_PORT}"

    def fis_start(self, **overrides: str) -> None:
        if overrides:
            # the unit reads the box's .env; an override runs FIS by hand
            exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in overrides.items())
            # setsid -f: the parent returns at once, so the ssh session's
            # stdout closes; a trailing `&` leaves a subshell holding it open
            self.ssh_fis(
                f"cd {self.fis_checkout} && {exports} setsid -f nohup .venv/bin/fis api"
                f" >> {self.ADHOC_LOG} 2>&1 < /dev/null"
            )
        else:
            self.ssh_fis("sudo systemctl start fis-api")
        self.wait_fis(up=True, within_s=30)

    def fis_stop(self) -> None:
        self.ssh_fis("sudo systemctl stop fis-api; pkill -u fis -f '[f]is api' || true")
        self.wait_fis(up=False, within_s=10)

    def live_connections(self, principal: str) -> set[str]:
        out = self.ssh(
            self.broker_login,
            f"docker exec {self.container} rabbitmqctl -q list_connections user name",
        )
        return self.connection_names(out, principal)

    def principal_status(self, principal: str, verb: str) -> None:
        self.ssh_fis(f"cd {self.fis_checkout} && .venv/bin/fis principal {verb} {shlex.quote(principal)}")

    def close(self) -> None:
        """FIS back under systemd; the journal since this run started, plus
        any ad-hoc log, as the run's fis log; the tunnel down."""
        self.fis_stop()
        self.fis_start()
        journal = self.ssh_fis(
            f"journalctl -u fis-api --utc --no-pager -o short-iso --since {shlex.quote(self.started_utc)};"
            f" if [ -f {self.ADHOC_LOG} ]; then echo '--- ad-hoc fis api ---'; cat {self.ADHOC_LOG}; rm {self.ADHOC_LOG}; fi"
        )
        self.fis_log_path.write_text(journal)
        self.tunnel.terminate()
        self.tunnel.wait(timeout=10)


def rig_from_env(run_dir: Path, fis_log_name: str = "fis.log") -> Rig:
    kind = _env("BATTERY_RIG", "local")
    if kind == "remote":
        return RemoteRig(run_dir, fis_log_name)
    if kind == "local":
        return LocalRig(run_dir, fis_log_name)
    raise ValueError(f"BATTERY_RIG={kind!r}: local or remote")
