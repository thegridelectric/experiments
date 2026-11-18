#!/usr/bin/env python3
"""The temperatures, powers and flows of the running stack over time, as
the scada reported them.

    uv run python plot_channels.py

Run from this folder with the stack up. Reads every reading the scada has
persisted since it started (through `channel_readings.py`, inside the
scada's container) and writes, under `logs/`:

- `channels.png`: three graphs on one time axis, every temperature, every
  power and every flow, a line per channel;
- `tank-temps.png`: the buffer and the store tanks, a panel per tank and a
  line per depth;
- `distribution.png`: the distribution loop on its own, the zone
  temperatures, the supply and return water, the flow and the zone calls;
- `channels.csv`: the readings all three are drawn from.

Prints the paths of the pictures. A power channel is reported when it
changes, so its line holds each value until the next.
"""

import csv
import io
import subprocess
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

HERE = Path(__file__).parent
LOGS = HERE / "logs"
LINE_STYLES = ("-", "--", ":")


class Kind(StrEnum):
    """What a channel measures, as `channel_readings.py` sorts them."""

    temperature = "temperature"
    power = "power"
    flow = "flow"


AXIS_LABEL = {
    Kind.temperature: "temperature (°C)",
    Kind.power: "power (W)",
    Kind.flow: "flow (US gpm)",
}


class Reading(NamedTuple):
    """One reading in display units, a row of `channel_readings.py`'s
    output. Interior to the plot; the word it is read from is
    channel.readings."""

    at: datetime
    channel: str
    kind: Kind
    value: float
    tank: str | None
    depth: int | None


def channel_readings() -> list[Reading]:
    done = subprocess.run(
        ["docker", "compose", "exec", "-T", "scada", "python", "-"],
        cwd=HERE,
        input=(HERE / "channel_readings.py").read_text(),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        (LOGS / "plot_channels.stderr").write_text(done.stderr)
        print(f"ABORT the scada cannot be read: see {LOGS / 'plot_channels.stderr'}")
        sys.exit(2)
    (LOGS / "channels.csv").write_text(done.stdout)
    return [
        Reading(
            datetime.fromtimestamp(int(row["unix_s"]), UTC),
            row["channel"],
            Kind(row["kind"]),
            float(row["value"]),
            row["tank"] or None,
            int(row["depth"]) if row["depth"] else None,
        )
        for row in csv.DictReader(io.StringIO(done.stdout))
    ]


def label_time(axis: Axes) -> None:
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %H:%M", tz=UTC))
    axis.set_xlabel("UTC")


def plot_by_kind(readings: list[Reading]) -> Path:
    end = max(one.at for one in readings)
    figure, axes = plt.subplots(len(Kind), 1, sharex=True, figsize=(15, 14))
    for axis, kind in zip(axes, Kind, strict=True):
        lines: dict[str, list[Reading]] = {}
        for one in readings:
            if one.kind == kind:
                lines.setdefault(one.channel, []).append(one)
        colours = plt.get_cmap("tab10")
        for index, (channel, line) in enumerate(sorted(lines.items())):
            times = [one.at for one in line]
            values = [one.value for one in line]
            if kind == Kind.power:
                times.append(end)
                values.append(values[-1])
            axis.plot(
                times,
                values,
                label=channel,
                linewidth=1,
                color=colours(index % 10),
                linestyle=LINE_STYLES[index // 10 % len(LINE_STYLES)],
                drawstyle="steps-post" if kind == Kind.power else "default",
            )
        axis.set_ylabel(AXIS_LABEL[kind])
        axis.grid(alpha=0.3)
        axis.legend(loc="upper left", bbox_to_anchor=(1.005, 1), fontsize="small")
    label_time(axes[-1])
    figure.tight_layout()
    path = LOGS / "channels.png"
    figure.savefig(path, dpi=120)
    return path


def plot_tanks(readings: list[Reading]) -> Path:
    in_tanks = [one for one in readings if one.tank is not None]
    tanks = list(dict.fromkeys(one.tank for one in in_tanks))
    figure, grid = plt.subplots(
        len(tanks),
        1,
        sharex=True,
        sharey=True,
        squeeze=False,
        figsize=(11, 2.2 * len(tanks) + 1),
    )
    axes = grid[:, 0]
    for axis, tank in zip(axes, tanks, strict=True):
        in_tank = [one for one in in_tanks if one.tank == tank]
        for depth in sorted({one.depth for one in in_tank if one.depth is not None}):
            line = [one for one in in_tank if one.depth == depth]
            axis.plot(
                [one.at for one in line],
                [one.value for one in line],
                label=f"depth {depth}",
                linewidth=1,
            )
        axis.set_ylabel(f"{tank} (°C)")
        axis.grid(alpha=0.3)
    axes[0].legend(loc="upper left", ncols=3, fontsize="small")
    label_time(axes[-1])
    figure.tight_layout()
    path = LOGS / "tank-temps.png"
    figure.savefig(path, dpi=120)
    return path


def lines_of(readings: list[Reading], channels: set[str]) -> dict[str, list[Reading]]:
    found: dict[str, list[Reading]] = {}
    for one in readings:
        if one.channel in channels:
            found.setdefault(one.channel, []).append(one)
    return found


def draw(
    axis: Axes, lines: dict[str, list[Reading]], *, steps: bool, end: datetime
) -> None:
    for channel, line in sorted(lines.items()):
        times = [one.at for one in line]
        values = [one.value for one in line]
        if steps:
            times.append(end)
            values.append(values[-1])
            axis.plot(mdates.date2num(times), values, label=channel, linewidth=1, drawstyle="steps-post")
        else:
            axis.plot(mdates.date2num(times), values, label=channel, linewidth=1)
    axis.grid(alpha=0.3)
    axis.legend(loc="upper left", fontsize="small")


def plot_distribution(readings: list[Reading]) -> Path:
    """The distribution loop: the zone temperatures, the water supplied to
    the house and returning from it, the flow, and the calls that run the pump."""
    end = max(one.at for one in readings)
    zones = lines_of(
        readings,
        {
            one.channel
            for one in readings
            if one.channel.startswith("zone") and one.kind == Kind.temperature
        },
    )
    water = lines_of(readings, {"dist-swt", "dist-rwt"})
    flow = lines_of(readings, {"dist-flow"})
    calls = lines_of(
        readings,
        {
            one.channel
            for one in readings
            if one.channel in {"dist-pump-pwr"}
            or one.channel.endswith("-whitewire-pwr")
        },
    )
    figure, grid = plt.subplots(4, 1, sharex=True, squeeze=False, figsize=(12, 10))
    panels = (
        (zones, False, "zone (°C)"),
        (water, False, "distribution water (°C)"),
        (flow, False, "flow (US gpm)"),
        (calls, True, "call (W)"),
    )
    for axis, (lines, steps, label) in zip(grid[:, 0], panels, strict=True):
        draw(axis, lines, steps=steps, end=end)
        axis.set_ylabel(label)
    label_time(grid[-1, 0])
    figure.tight_layout()
    path = LOGS / "distribution.png"
    figure.savefig(path, dpi=120)
    return path


def main() -> int:
    LOGS.mkdir(exist_ok=True)
    readings = channel_readings()
    if not readings:
        print("ABORT the scada has reported no temperature, power or flow yet")
        return 2
    print(plot_by_kind(readings))
    print(plot_tanks(readings))
    print(plot_distribution(readings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
