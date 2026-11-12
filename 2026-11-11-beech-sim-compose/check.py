#!/usr/bin/env python3
"""The verdict on the running stack: is the loop between the scada and the
plant closed, both ways.

    ./check.py

Run from this folder once the stack is up. The scada reports each minute
and the verdict needs two reports, so a check on a stack just started
waits for them, up to five minutes, saying so on stderr. Then it reads
the state of the four services, what the plant logged it heard, and what
the scada persisted (through `stack_check.py`, inside the scada's
container). Writes `logs/` and prints one line: PASS or FAIL and the path
of the verdict. `logs/scada-control.log` is the lines of the scada's log
from its control actors; the whole of it is `logs/scada.log`.

What the plant heard is read off its log, line by line: the plant keeps no
other record of an actuation.
"""

import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
LOGS = HERE / "logs"
SERVICES = ("rabbit", "mosquitto", "plant", "scada")
REPOS = ("gridworks-scada", "gridworks-terminalasset")
CONTROL = ("[sieg-loop]", "[lc]", "[hp-boss]", "Glitch", "Top state")
HEARD = re.compile(r"heard (\S+) (Energize|DeEnergize)$")
CONSUMING = re.compile(r"consuming; (\d+) channels every")
HP_STANDBY_W = 20
REPORTS_NEEDED = 2
WAIT_FOR_REPORTS_S = 300
POLL_S = 10


class Heard(NamedTuple):
    """One actuation the plant logged. Interior to this check; the word on
    the wire is sim.plant.actuation, which the plant does not keep."""

    relay: str
    action: str


def run_compose(
    *args: str, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=HERE,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def compose(*args: str, stdin: str | None = None) -> str:
    done = run_compose(*args, stdin=stdin)
    if done.returncode != 0:
        (LOGS / "check.stderr").write_text(done.stderr)
        print(f"ABORT docker compose {' '.join(args)}: see {LOGS / 'check.stderr'}")
        sys.exit(2)
    return done.stdout


def scada_reported() -> dict:
    """What `stack_check.py` reads inside the scada's container, once the
    scada has persisted the reports the verdict needs or the wait for them
    has run out. A scada that cannot be read yet counts as not ready."""
    script = (HERE / "stack_check.py").read_text()
    deadline = time.monotonic() + WAIT_FOR_REPORTS_S
    while True:
        done = run_compose("exec", "-T", "scada", "python", "-", stdin=script)
        reports = json.loads(done.stdout)["reports"] if done.returncode == 0 else 0
        if reports >= REPORTS_NEEDED or time.monotonic() >= deadline:
            break
        print(
            f"waiting for the scada's reports: {reports} of {REPORTS_NEEDED}",
            file=sys.stderr,
        )
        time.sleep(POLL_S)
    if done.returncode != 0:
        (LOGS / "check.stderr").write_text(done.stderr)
        print(f"ABORT the scada cannot be read: see {LOGS / 'check.stderr'}")
        sys.exit(2)
    return json.loads(done.stdout)


def code_under_test() -> list[str]:
    lines = []
    for repo in REPOS:
        path = HERE.parent.parent / repo
        sha = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        lines.append(f"{repo} {sha} {len(dirty)} dirty")
    return lines


def main() -> int:
    LOGS.mkdir(exist_ok=True)
    reported = scada_reported()
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    states = {
        service["Service"]: service
        for service in map(
            json.loads, compose("ps", "--all", "--format", "json").splitlines()
        )
    }
    plant_log = compose("logs", "--no-color", "--no-log-prefix", "plant")
    scada_log = compose("logs", "--no-color", "--no-log-prefix", "scada")
    (LOGS / "plant.log").write_text(
        "".join(
            line
            for line in plant_log.splitlines(keepends=True)
            if "LOG_SOLVER" not in line
        )
    )
    (LOGS / "scada.log").write_text(scada_log)
    (LOGS / "scada-control.log").write_text(
        "".join(
            line
            for line in scada_log.splitlines(keepends=True)
            if any(mark in line for mark in CONTROL)
        )
    )
    (LOGS / "code-under-test.txt").write_text("\n".join(code_under_test()) + "\n")
    (LOGS / "reports.json").write_text(json.dumps(reported, indent=1) + "\n")

    heard = [
        Heard(*match.groups())
        for line in plant_log.splitlines()
        if (match := HEARD.search(line))
    ]
    consuming = CONSUMING.search(plant_log)
    seen = reported["seen"]
    plant_fed = set(reported["plant_fed_channels"])
    relays = set(reported["relays"])
    changed = sorted(
        name for name in plant_fed & set(seen) if seen[name]["distinct_values"] > 1
    )
    started = {name: states[name]["CreatedAt"] for name in SERVICES if name in states}
    checks = {
        "the four services are running": all(
            states.get(name, {}).get("State") == "running" for name in SERVICES
        ),
        "the scada has not shut down": reported["shutdown_reasons"] == [],
        "the plant shows every channel the scada takes from it": consuming is not None
        and int(consuming.group(1)) == len(plant_fed),
        "the plant heard every relay of the layout": relays
        <= {one.relay for one in heard},
        "the scada reported for two minutes or more": reported["reports"]
        >= REPORTS_NEEDED,
        "every plant-fed channel is in the reports": plant_fed <= set(seen),
        "plant-fed channels moved": len(changed) > 0,
    }
    actions: dict[str, dict[str, int]] = {}
    for one in heard:
        counts = actions.setdefault(one.relay, {"Energize": 0, "DeEnergize": 0})
        counts[one.action] += 1
    result = {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checked_at_utc": checked_at,
        "services_created_at": started,
        "checks": checks,
        "reports": reported["reports"],
        "reports_the_snapshot_refuses": reported["reports_the_snapshot_refuses"],
        "first_refusal": reported["first_refusal"],
        "plant_fed_channels": len(plant_fed),
        "plant_fed_channels_that_moved": len(changed),
        "actuations_heard": len(heard),
        "actuations_by_relay": dict(sorted(actions.items())),
        "the_heat_pump_ran": seen.get("hp-odu-pwr", {}).get("high", 0) > HP_STANDBY_W,
        "seen": {name: seen[name] for name in sorted(plant_fed & set(seen))},
    }
    path = LOGS / "check.json"
    path.write_text(json.dumps(result, indent=1) + "\n")
    print(f"{result['verdict']} {path}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
