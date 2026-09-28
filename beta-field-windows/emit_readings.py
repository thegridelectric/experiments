"""Emit the gw.readings instance for one run of a field window.

The run folder holds the report.events the window scada persisted
(`<house>-events/`), each a slot of channel.readings. This folds every slot
into one gw.readings for the window: the terminal asset's alias from the
reports, the window as the first slot's start to the last slot's end, the
channel words (data.channel.gt / derived.channel.gt) taken from the house's
tlayouts gen output for exactly the channels that have readings, and one
channel.readings per channel with the slots' readings concatenated in time
order.

    uv run python beta-field-windows/emit_readings.py <run folder> <house>

Written as its dict form and read back through the codec, so the file on
disk is what validates.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import (  # noqa: E402
    ChannelReadings,
    DataChannelGt,
    DerivedChannelGt,
    GwReadings,
)

TLAYOUTS = HERE.parent.parent / "tlayouts" / "output"


def report_payloads(events_dir: Path) -> list[dict]:
    reports = []
    for path in sorted(events_dir.rglob("*.json")):
        event = json.loads(path.read_text())
        if event.get("TypeName") == "report.event":
            reports.append(event["Report"])
    if not reports:
        raise SystemExit(f"{events_dir}: no report.event")
    return reports


def main(run_dir: Path, house: str) -> None:
    codec = SemaCodec()
    reports = report_payloads(run_dir / f"{house}-events")
    layout = json.loads(
        (TLAYOUTS / house / "hardware-layout.generated.json").read_text()
    )
    words: dict[str, DataChannelGt | DerivedChannelGt] = {}
    for d in layout["DataChannels"]:
        words[d["Name"]] = codec.from_dict(d, expect=DataChannelGt)
    for d in layout["DerivedChannels"]:
        words[d["Name"]] = codec.from_dict(d, expect=DerivedChannelGt)

    ta_alias = {r["AboutGNodeAlias"] for r in reports}
    if len(ta_alias) != 1:
        raise SystemExit(f"reports name more than one terminal asset: {ta_alias}")
    start_ms = min(r["SlotStartUnixS"] for r in reports) * 1000
    end_ms = max(r["SlotStartUnixS"] + r["SlotDurationS"] for r in reports) * 1000

    pairs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in reports:
        for cr in r["ChannelReadingList"]:
            pairs[cr["ChannelName"]].extend(
                zip(cr["ScadaReadTimeUnixMsList"], cr["ValueList"])
            )
    missing = sorted(set(pairs) - set(words))
    if missing:
        raise SystemExit(f"readings for channels the layout does not name: {missing}")

    readings = GwReadings(
        ta_alias=ta_alias.pop(),
        start_unix_ms=start_ms,
        end_unix_ms=end_ms,
        channels=[words[name] for name in sorted(pairs)],
        channel_readings_list=[
            ChannelReadings(
                channel_name=name,
                value_list=[v for _, v in sorted(pairs[name])],
                scada_read_time_unix_ms_list=[t for t, _ in sorted(pairs[name])],
            )
            for name in sorted(pairs)
        ],
    )
    out = run_dir / "instances" / f"{house}-gw.readings-000.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(readings.to_dict(), indent=1) + "\n")
    back = codec.from_dict(json.loads(out.read_text()), expect=GwReadings)
    n = sum(len(c.value_list) for c in back.channel_readings_list)
    print(f"{out}: {len(back.channels)} channels, {n} readings, {len(reports)} slots")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), sys.argv[2])
