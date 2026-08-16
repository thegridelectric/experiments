"""Does a fieldless sema lay-over base survive gwproto's discriminator machinery?

Builds a PATCHED COPY of the whole gwsproto package with GwsprotoSemaType
injected as the base of every named type, then compares the real
discriminated unions (message model + component/device-type decoders)
against the unpatched baseline. Nothing in the working tree is touched.

    python run.py            # exit 0 = every check passed
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCADA = Path(__file__).resolve().parents[2] / "gridworks-scada"
GWSPROTO_SRC = SCADA / "packages/gridworks-scada-protocol/src/gwsproto"
PY = SCADA / "gw_spaceheat/venv/bin/python"
WORK = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/layover-exp")

LAYOVER = '''"""The sema lay-over: identity accessors shared by every gwsproto sema word.

Fieldless and config-less BY DESIGN. gwproto's payload discovery
(gwproto/decoders.py get_candidate_payload_classes) includes a class only
if it declares a field literally named "TypeName" whose annotation is a
Literal -- so a base carrying no TypeName field is invisible to the
discriminated union, while its subclasses are discovered normally.
Declaring no model_config matters just as much: pydantic MERGES a base's
config into every subclass, so a frozen/extra-forbid base would silently
reconfigure all 149 words.
"""

from typing import Optional

from pydantic import BaseModel


class GwsprotoSemaType(BaseModel):
    """Base for gwsproto sema words. Method surface only -- no fields, no config."""

    @classmethod
    def type_name_value(cls) -> str:
        field = cls.model_fields.get("TypeName")
        if field is None:
            raise ValueError(f"{cls.__name__} has no TypeName field")
        return str(field.default)

    @classmethod
    def version_value(cls) -> Optional[str]:
        field = cls.model_fields.get("Version")
        return None if field is None else str(field.default)
'''

PROBE = r'''
import importlib, json, sys
from gwproto.decoders import pydantic_named_types

import gwsproto.named_types as nt

out = {}
out["message_union"] = sorted(
    t.model_fields["TypeName"].default
    for t in pydantic_named_types(module_names=["gwsproto.named_types"])
)
# per-word model_config, so a config leak from the base would show up
cfg = {}
for name in dir(nt):
    obj = getattr(nt, name)
    if isinstance(obj, type) and hasattr(obj, "model_config") and hasattr(obj, "model_fields"):
        if "TypeName" in getattr(obj, "model_fields", {}):
            cfg[name] = dict(sorted(obj.model_config.items()))
out["configs"] = cfg
try:
    out["n_component_types"] = len(pydantic_named_types(module_names=["gwsproto.data_classes.components"]))
except Exception as e:
    out["n_component_types"] = f"ERR {e}"

# does the lay-over exist here, and does every word expose it?
try:
    from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType
    out["layover_present"] = True
    words = [getattr(nt, n) for n in dir(nt)
             if isinstance(getattr(nt, n), type) and "TypeName" in getattr(getattr(nt, n), "model_fields", {})]
    out["n_words"] = len(words)
    out["n_words_with_base"] = sum(1 for w in words if issubclass(w, GwsprotoSemaType))
    out["n_type_name_value_ok"] = sum(
        1 for w in words
        if issubclass(w, GwsprotoSemaType) and w.type_name_value() == w.model_fields["TypeName"].default
    )
    out["layover_in_union"] = "GwsprotoSemaType" in [
        t.__name__ for t in pydantic_named_types(module_names=["gwsproto.named_types"])
    ]
except ImportError:
    out["layover_present"] = False
    words = [getattr(nt, n) for n in dir(nt)
             if isinstance(getattr(nt, n), type) and "TypeName" in getattr(getattr(nt, n), "model_fields", {})]
    out["n_words"] = len(words)

# real end-to-end: build the actual scada message model and round-trip a payload
from gwproto import create_message_model
from gwproto.messages import Ack, Ping
import gwproactor.message  # discovery requires it already imported
MM = create_message_model("ProbeDecoder", module_names=["gwsproto.named_types", "gwproactor.message"],
                          explicit_types=[Ack, Ping])
from gwsproto.named_types import CaptureTuning
ct = CaptureTuning(ChannelName="probe-chan", CapturePeriodS=60, AsyncCapture=True,
                   AsyncCaptureDelta=1, Exponent=0, Unit="Unitless")
out["roundtrip"] = json.loads(ct.model_dump_json(by_alias=True))
out["roundtrip_ok"] = CaptureTuning.model_validate(json.loads(ct.model_dump_json(by_alias=True))) == ct
print("@@JSON@@" + json.dumps(out, default=str))
'''


def probe(pkg_parent: Path | None, label: str) -> dict:
    env_path = str(pkg_parent) if pkg_parent else ""
    code = PROBE
    p = subprocess.run(
        [str(PY), "-c", code],
        capture_output=True, text=True, cwd=str(SCADA / "gw_spaceheat"),
        env={**__import__("os").environ,
             "PYTHONPATH": (env_path + ":" if env_path else "") + str(SCADA / "gw_spaceheat")},
    )
    if "@@JSON@@" not in p.stdout:
        print(f"--- {label} PROBE FAILED ---\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
        sys.exit(1)
    return json.loads(p.stdout.split("@@JSON@@", 1)[1].strip())


def build_patched(dest: Path) -> tuple[int, int]:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(GWSPROTO_SRC, dest / "gwsproto")
    (dest / "gwsproto/type_helpers/gwsproto_sema_type.py").write_text(LAYOVER)

    rewritten = files = 0
    IMPORT = "from gwsproto.type_helpers.gwsproto_sema_type import GwsprotoSemaType\n"
    for path in sorted((dest / "gwsproto/named_types").glob("*.py")):
        text = path.read_text()
        new, n = re.subn(r"^class (\w+)\(BaseModel\):", r"class \1(GwsprotoSemaType):",
                         text, flags=re.M)
        if n:
            new = IMPORT + new
            path.write_text(new)
            rewritten += n
            files += 1
    # words on an EXTERNAL base (gwproto's EventBase) take the lay-over as a
    # second base -- we do not own EventBase, so we cannot re-parent it.
    ev = dest / "gwsproto/named_types/events.py"
    t = ev.read_text()
    t2, n = re.subn(r"^class (\w+)\(EventBase\):", r"class \1(EventBase, GwsprotoSemaType):",
                    t, flags=re.M)
    if n:
        ev.write_text(IMPORT + t2)
        rewritten += n

    # the component base hierarchy: one edit reaches its 19 subclasses
    cb = dest / "gwsproto/type_helpers/component_base.py"
    t = cb.read_text()
    t2, n = re.subn(r"^class ComponentBase\(BaseModel\):",
                    "class ComponentBase(GwsprotoSemaType):", t, flags=re.M)
    if n:
        cb.write_text(IMPORT + t2)
        rewritten += n
    return rewritten, files


def main() -> int:
    print("== baseline (unpatched gwsproto) ==")
    base = probe(None, "baseline")
    print(f"   words with a Literal TypeName : {base['n_words']}")
    print(f"   types in the message union    : {len(base['message_union'])}")
    print(f"   lay-over present              : {base['layover_present']}")

    print("\n== building patched copy ==")
    n_classes, n_files = build_patched(WORK)
    print(f"   rewrote {n_classes} class declarations across {n_files} files (+ ComponentBase)")
    print(f"   patched package at {WORK}/gwsproto")

    print("\n== patched (lay-over on every word) ==")
    pat = probe(WORK, "patched")
    print(f"   words with a Literal TypeName : {pat['n_words']}")
    print(f"   types in the message union    : {len(pat['message_union'])}")
    print(f"   words inheriting the lay-over : {pat['n_words_with_base']}")
    print(f"   type_name_value() correct     : {pat['n_type_name_value_ok']}")
    print(f"   lay-over itself in the union  : {pat['layover_in_union']}")

    print("\n== checks ==")
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok &= cond
        print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail and not cond else ''}")

    missing = set(base["message_union"]) - set(pat["message_union"])
    added = set(pat["message_union"]) - set(base["message_union"])
    check("message union identical", not missing and not added,
          f"missing={sorted(missing)[:5]} added={sorted(added)[:5]}")
    check("lay-over invisible to discovery", pat["layover_in_union"] is False)
    check("every word inherits the lay-over",
          pat["n_words_with_base"] == pat["n_words"],
          f"{pat['n_words_with_base']}/{pat['n_words']}")
    check("type_name_value() correct on every word",
          pat["n_type_name_value_ok"] == pat["n_words"],
          f"{pat['n_type_name_value_ok']}/{pat['n_words']}")

    cfg_changed = {k: (base["configs"].get(k), pat["configs"].get(k))
                   for k in set(base["configs"]) | set(pat["configs"])
                   if base["configs"].get(k) != pat["configs"].get(k)}
    check("no model_config leaked into any word", not cfg_changed,
          f"{list(cfg_changed)[:5]}")
    check("component-type discovery unchanged",
          base["n_component_types"] == pat["n_component_types"],
          f"{base['n_component_types']} -> {pat['n_component_types']}")
    check("payload round-trips", pat["roundtrip_ok"] is True)
    check("wire form unchanged", base["roundtrip"] == pat["roundtrip"],
          f"{base['roundtrip']} != {pat['roundtrip']}")

    print(f"\n== {'ALL CHECKS PASSED' if ok else 'FAILURES PRESENT'} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
