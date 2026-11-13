"""Parse the window log's `[sieg-loop] sieg-view` lines into sieg-view.csv.

One row per line: box time, loop state, and the strip's values with their
reading ages dropped and units stripped; a `--` (no reading yet) is an
empty cell.
"""

import re
from pathlib import Path

HERE = Path(__file__).parent
LOG = HERE / "maple-window-20260928-071602.log"
OUT = HERE / "sieg-view.csv"
LINE = re.compile(r"^(\S+ \S+) \[sieg-loop\] sieg-view (\S+) (.*)$")
PAIR = re.compile(r"([\w\-\*]+)=([^\s]+)")
COLUMNS = [
    ("hp_odu_pwr_w", "hp-odu-pwr"), ("hp_lwt_f", "hp-lwt"), ("hp_ewt_f", "hp-ewt"),
    ("lift_f", "lift"), ("sieg_flow_gpm", "sieg-flow"),
    ("sieg_send_flow_gpm", "sieg-send-flow"), ("primary_flow_gpm", "primary-flow"),
    ("sieg_hot_f", "sieg-hot"), ("sieg_cold_f", "sieg-cold"),
    ("buffer_hot_pipe_f", "buffer-hot-pipe"), ("store_hot_pipe_f", "store-hot-pipe"),
]


def cell(raw: str) -> str:
    v = re.sub(r"@\d+s$", "", raw)
    return "" if v == "--" else v.rstrip("FWgpm")


def main() -> None:
    rows = ["time,state," + ",".join(h for h, _ in COLUMNS)]
    for line in LOG.read_text().splitlines():
        m = LINE.match(line)
        if m is None:
            continue
        stamp, state, rest = m.groups()
        kv = {k.rstrip("*"): cell(v) for k, v in PAIR.findall(rest)}
        rows.append(",".join([stamp[11:19], state] + [kv.get(k, "") for _, k in COLUMNS]))
    OUT.write_text("\n".join(rows) + "\n")
    print(f"{OUT.name}: {len(rows) - 1} rows")


if __name__ == "__main__":
    main()
