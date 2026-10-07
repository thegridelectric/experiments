#!/usr/bin/env python3
"""Emit one gw.experiment.run instance per house, THROUGH the vendored
snapshot. The window is the one each hourly file states. Findings stay
in the README, steady-drop.txt and the hourly files (kind-specific; no
word)."""

import datetime
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.types import GwExperimentRun  # noqa: E402
from pull_readings import ET  # noqa: E402


def et_midnight_ms(day: str) -> int:
    d = datetime.date.fromisoformat(day)
    return int(datetime.datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() * 1000)


def main() -> None:
    out_dir = HERE / "instances"
    out_dir.mkdir(exist_ok=True)
    for path in sorted(HERE.glob("*-hourly.dist.json")):
        doc = json.loads(path.read_text())
        scada = doc["TaAlias"].removesuffix(".ta") + ".scada"
        inst = GwExperimentRun(
            experiment_slug="mix-or-not",
            host_g_node_alias=scada,
            start_unix_ms=et_midnight_ms(doc["StartDayEt"]),
            end_unix_ms=et_midnight_ms(doc["EndDayEt"]),
            code_ref="emitter_drop.py",
        )
        out = out_dir / f"{scada}-gw.experiment.run-000.json"
        out.write_text(json.dumps(inst.to_dict(), indent=1) + "\n")
        print(f"wrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
