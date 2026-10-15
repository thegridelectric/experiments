#!/usr/bin/env python3
"""Import spruce's `gw.nolan.layout` word into this folder from the
tlayouts gen output, upgraded to the vendored snapshot's binding.

Spruce emits only `layout.lite` to the journal, which has no zone
circuits, so the layout word the fit reads its slab zones from is the
tlayouts generator's output for the house. Every nested word in it
(channels, components, device types) is decoded through the codec with
auto-upgrade and re-serialized, so the instance written here validates
against the registry the snapshot was built from even when the
generator's own snapshot is behind.

Filename grammar `<subject>-<type.name>-<version>.json`, subject the
scada alias the layout belongs to.

  uv run python import_layout.py ../../tlayouts/output/spruce/gw.nolan.layout.json
"""

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwNolanLayout  # noqa: E402
from naming import validate_lrd  # noqa: E402

SCADA = validate_lrd("hw1.isone.me.versant.keene.spruce.scada")


def upgraded(codec: SemaCodec, node: Any) -> Any:
    """The node with every nested sema word (a dict with TypeName and
    Version) decoded through the codec, upgraded to the snapshot's
    latest version and re-serialized; children before parents."""
    if isinstance(node, list):
        return [upgraded(codec, x) for x in node]
    if isinstance(node, dict):
        inner = {k: upgraded(codec, v) for k, v in node.items()}
        if "TypeName" in inner and "Version" in inner and inner["TypeName"] in codec.registry:
            return codec.from_dict(inner).to_dict()
        return inner  # a plain mapping, or a word inside an opaque parameters field
    return node


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    codec = SemaCodec()
    raw = json.loads(Path(sys.argv[1]).read_text())
    layout = codec.from_dict(upgraded(codec, raw), expect=GwNolanLayout)
    out = HERE / f"{SCADA}-{layout.type_name}-{layout.version}.json"
    out.write_text(json.dumps(layout.to_dict(), indent=1) + "\n")
    back = codec.from_dict(json.loads(out.read_text()), expect=GwNolanLayout)
    assert back == layout, out
    circuits = layout.hydronic.zone_call_circuits
    print(f"wrote {out.name}: {len(circuits)} zone-call circuits, "
          f"{len(layout.data_channels)} data channels, {len(layout.derived_channels)} derived")


if __name__ == "__main__":
    main()
