"""make_imaginary_layout.py — the magical wand that makes real things imaginary.

Takes a REAL hardware layout (a real house, with real identities) and returns an
IMAGINARY one: every *instance* UUID is replaced with a fresh, unique UUID, so the
layout no longer claims to be the real house — while every *device-type* UUID is set
to its canonical value (the UUID `CACS_BY_MAKE_MODEL` pins to that MakeModel), because
device types are real, shared identities, not instance identity. References stay
consistent (each distinct old id maps to one new id, replaced everywhere it occurs —
that *is* the uuid DAG: ids are nodes, every reference is an edge, and swapping a node's
id preserves all its edges). This is the sim/real boundary as a tool: a simulated scada
should not be able to wear a real house's identity.

Bonus: it also refreshes a *stale* layout's type versions/fields to current, so an old
generated layout (e.g. a Feb `oak.generated.json`) loads against today's types.

Respecting uniqueness: instance ids are unique (one fresh uuid4 each); device types are
deduplicated to one canonical id per MakeModel (shared, as they should be). The output
is validated by actually loading it as a House0Layout before it is written.

Usage:
  PYTHONPATH=<scada>/gw_spaceheat python make_imaginary_layout.py REAL.json IMAGINARY.json
"""

import json
import re
import sys
import uuid

from gwsproto.type_helpers.cacs_by_make_model import CACS_BY_MAKE_MODEL
from gwsproto.enums import MakeModel, TelemetryName
from gwsproto.enums.unit_quantity import UNIT_TO_QUANTITY

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

SCADA = "/Users/jessica/GridWorks/gridworks-scada"


def refresh_versions(doc):
    """Bring a stale layout up to current type versions/fields (in place)."""
    def walk(o):
        if isinstance(o, dict):
            tn = o.get("TypeName")
            if tn == "i2c.multichannel.dt.relay.component.gt":
                o["Version"] = "004"
                o.setdefault("I2cBus", "default")  # placeholder; oak predates Gw108/I2cBus
                for cfg in o.get("ConfigList", []):
                    cfg["Version"] = "003"
                    if cfg.get("AsyncCapture") and not cfg.get("AsyncCaptureDelta"):
                        cfg["AsyncCaptureDelta"] = 1
            elif tn == "spaceheat.node.gt":
                o["Version"] = "301"
            elif tn == "derived.channel.gt":
                o["Version"] = "001"
                # strategy renames from the derived-channel rework
                o["Strategy"] = {"linear-fit": "affine", "layer-by-layer": "system-model"}.get(
                    o.get("Strategy"), o.get("Strategy"))
                if "EmissionMethod" not in o:
                    o["EmissionMethod"] = {
                        "identity": "OnTrigger",
                        "affine": "OnTrigger",
                        "system-model": "Periodic",
                        "heat-call": "AsyncAndPeriodic",
                        "simple-falling-edge-setpoint": "AsyncAndPeriodic",
                    }.get(o.get("Strategy"), "OnTrigger")
            elif tn == "data.channel.gt":
                o["Version"] = "002"
                if "Quantity" not in o:
                    # canonical projection (the same map Axiom 2 enforces)
                    o["Quantity"] = UNIT_TO_QUANTITY[TelemetryName(o["TelemetryName"])].value
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for i in o:
                walk(i)
    walk(doc)


def make_imaginary(doc):
    """Re-ID: device-type ids -> canonical (by MakeModel); all other ids -> fresh."""
    cac_canon = {}  # old device-type id -> canonical id

    def find_cacs(o):
        if isinstance(o, dict):
            tn = o.get("TypeName", "")
            if tn.endswith("cac.gt") or tn == "component.attribute.class.gt":
                old = o.get("ComponentAttributeClassId")
                mm = o.get("MakeModel")
                if old and mm is not None:
                    member = MakeModel(mm)
                    if member in CACS_BY_MAKE_MODEL:
                        cac_canon[old] = str(CACS_BY_MAKE_MODEL[member])
                    # else: unpinned device type (e.g. UNKNOWN) — falls through to a
                    # fresh instance id in the general pass; references stay consistent
            for v in o.values():
                find_cacs(v)
        elif isinstance(o, list):
            for i in o:
                find_cacs(i)
    find_cacs(doc)

    all_ids = set()

    def collect(o):
        if isinstance(o, dict):
            for v in o.values():
                collect(v)
        elif isinstance(o, list):
            for i in o:
                collect(i)
        elif isinstance(o, str) and UUID_RE.match(o):
            all_ids.add(o)
    collect(doc)

    idmap = {}
    for i in all_ids:
        idmap[i] = cac_canon[i] if i in cac_canon else str(uuid.uuid4())

    # uniqueness: fresh instance ids must not collide with each other or canonicals
    fresh = [v for k, v in idmap.items() if k not in cac_canon]
    assert len(fresh) == len(set(fresh)), "fresh id collision (should be impossible)"

    def apply(o):
        if isinstance(o, dict):
            return {k: apply(v) for k, v in o.items()}
        if isinstance(o, list):
            return [apply(i) for i in o]
        if isinstance(o, str):
            return idmap.get(o, o)
        return o
    return apply(doc), idmap, cac_canon


def main():
    real_path, out_path = sys.argv[1], sys.argv[2]
    doc = json.load(open(real_path))
    refresh_versions(doc)
    imaginary, idmap, cac_canon = make_imaginary(doc)

    # validate by loading
    from gwsproto.data_classes.house_0_layout import House0Layout
    tmp = "/tmp/_imaginary_validate.json"
    json.dump(imaginary, open(tmp, "w"))
    lay = House0Layout.load(tmp)

    json.dump(imaginary, open(out_path, "w"), indent=2)
    print(f"wand: {real_path} -> {out_path}")
    print(f"  instance ids re-randomized : {len(idmap) - len(cac_canon)}")
    print(f"  device-type ids canonical  : {len(cac_canon)}")
    print(f"  validated load: {len(lay.nodes)} nodes, {len(lay.data_channels)} channels")


if __name__ == "__main__":
    main()
