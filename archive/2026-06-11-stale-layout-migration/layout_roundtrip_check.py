#!/usr/bin/env python
"""Cross-carrier round-trip check for the layout-vocabulary sweep.

Take a real scada-format layout JSON (scada-authored / scada-emitted), pull out
every instance by TypeName, and decode each through the SEMA runtime
(`default_codec.from_dict`). A clean decode is the cross-carrier guarantee that
the scada's wire form conforms to the new sema type.

Run from the sema repo so `sema` imports resolve:
    cd /Users/jessica/GridWorks/sema && \
      uv run python /Users/jessica/GridWorks/sim-time-experiment/layout_roundtrip_check.py \
      <layout.json> [TypeName ...]

With no TypeName filter it tries every TypeName sema knows; unknown-to-sema types
are reported as SKIP (not in runtime yet), real decode failures as FAIL.
"""
import json
import sys

from sema.runtime.codec import default_codec


def collect(obj, acc):
    if isinstance(obj, dict):
        tn = obj.get("TypeName")
        if tn:
            acc.setdefault(tn, []).append(obj)
        for v in obj.values():
            collect(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect(v, acc)


def main():
    layout_path = sys.argv[1]
    wanted = set(sys.argv[2:])
    with open(layout_path) as f:
        data = json.load(f)
    acc = {}
    collect(data, acc)

    n_pass = n_fail = n_skip = 0
    for tn in sorted(acc):
        if wanted and tn not in wanted:
            continue
        for i, inst in enumerate(acc[tn]):
            ver = inst.get("Version", "-")
            try:
                default_codec.from_dict(inst)
                print(f"PASS  {tn}:{ver}  [{i}]")
                n_pass += 1
            except Exception as e:  # noqa: BLE001
                msg = str(e).splitlines()[0][:160]
                tag = "SKIP" if "no registered" in str(e).lower() or "unknown" in str(e).lower() else "FAIL"
                print(f"{tag}  {tn}:{ver}  [{i}] -> {type(e).__name__}: {msg}")
                if tag == "FAIL":
                    n_fail += 1
                else:
                    n_skip += 1
    print(f"\n== {n_pass} PASS, {n_fail} FAIL, {n_skip} SKIP (from {layout_path}) ==")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
