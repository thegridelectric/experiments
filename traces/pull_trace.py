#!/usr/bin/env python3
"""Materialise an executor trace's input from the journal DB.

A trace spec (`wiki/<domain>/executor/traces/<name>/trace.yaml`) names a
window, the senders, which types keep their bodies, and the tracked set as
a forest fixture. This script writes, under `experiments/traces/<domain>/
<name>/` (gitignored):

  messages.jsonl   one message per line, ordered by arrival (persisted_at):
                   {"t", "from", "type", "body" | null, "refused"?}
  .snapshot/       a sema snapshot built from the executor's seed copy, the
                   codec every body is decoded through

and, once, `forest.json` beside the spec: the latest journaled
`g.node.forest` before the window, restricted to the subtree the spec
names. The forest is a declared input, so it lives with the spec and is
never overwritten.

Every body either decodes through the snapshot or is recorded on its row
as a refusal; a refusal is wire behaviour the replay must reproduce.

Usage (from experiments/):
  uv run traces/pull_trace.py ../wiki/gridworks-alerter/executor/traces/2026-10-15-oak-ltn-stop/trace.yaml

Env: GJK_DB_URL in experiments/.env; SEMA_REPO (default: sibling ../sema,
clean worktree, the sema CLI refuses a dirty one).
"""

import argparse
import datetime
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spot_check import db_url  # noqa: E402

EXPERIMENTS = Path(__file__).resolve().parents[1]
UMBRELLA = EXPERIMENTS.parent
FOREST_TYPE = "g.node.forest"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", type=Path, help="path to the trace.yaml in the wiki")
    return p.parse_args()


def domain_of(spec: Path) -> str:
    """wiki/<domain>/executor/traces/<name>/trace.yaml -> <domain>."""
    parts = spec.resolve().parts
    i = parts.index("executor")
    return parts[i - 1]


def as_utc(value: str | datetime.datetime) -> datetime.datetime:
    """A spec timestamp: YAML gives a datetime for `2026-10-15T18:50:00Z`, a str otherwise."""
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def iso(ts: datetime.datetime) -> str:
    return ts.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def build_snapshot(seed: Path, out: Path, package: str) -> Path:
    """Build a snapshot from the executor's seed copy; return the dir to put on sys.path."""
    sema_repo = Path(os.environ.get("SEMA_REPO", UMBRELLA / "sema")).resolve()
    if not sema_repo.is_dir():
        raise SystemExit(f"sema repo not found at {sema_repo}; set SEMA_REPO")
    subprocess.run(["uv", "run", "sema", "snapshot", "prepare", str(seed)], cwd=sema_repo, check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["uv", "run", "sema", "snapshot", "build", "--package-name", package], cwd=sema_repo,
                   check=True, stdout=subprocess.DEVNULL)
    pkg_dir = out / ".snapshot" / package
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    shutil.copytree(sema_repo / "output" / "sema", pkg_dir / "sema")
    (pkg_dir / "__init__.py").touch()
    return out / ".snapshot"


def restrict_forest(forest: dict, subtree: str) -> dict:
    """Keep the subtree's nodes and their ancestors; keep edges among the kept ids."""
    def keep(alias: str) -> bool:
        return subtree.startswith(alias + ".") or alias == subtree or alias.startswith(subtree + ".")
    nodes = [n for n in forest["Nodes"] if keep(n["Alias"])]
    ids = {n["GNodeId"] for n in nodes}
    edges = forest.get("Edges")
    if isinstance(edges, dict):
        edges = {k: v for k, v in edges.items() if k in ids}
    elif isinstance(edges, list):
        edges = [e for e in edges if all(v in ids for v in e.values() if isinstance(v, str))]
    return {**forest, "Nodes": nodes, "Edges": edges}


def main() -> None:
    args = parse_args()
    spec_path = args.spec.resolve()
    spec = yaml.safe_load(spec_path.read_text())
    domain = domain_of(spec_path)
    name = spec["name"]
    out = EXPERIMENTS / "traces" / domain / name
    out.mkdir(parents=True, exist_ok=True)
    seed = spec_path.parents[2] / "sema_seed_request.yaml"
    if not seed.exists():
        raise SystemExit(f"executor seed copy missing: {seed}")

    start, end = (as_utc(spec["window"][k]) for k in ("start", "end"))
    senders = list(spec["senders"])
    bodies_for = set(spec["bodies_for"])
    subtree = spec["tracked_set"]["subtree"]
    forest_path = spec_path.parent / spec["tracked_set"]["forest"]

    sys.path.insert(0, str(build_snapshot(seed, out, f"trace_{domain.replace('-', '_')}")))
    codec_mod = importlib.import_module(f"trace_{domain.replace('-', '_')}.sema.codec")
    codec = codec_mod.SemaCodec()

    def decode(body: dict) -> str | None:
        try:
            codec.from_dict(body)
            return None
        except Exception as e:  # noqa: BLE001 - the refusal text is the record
            return str(e).splitlines()[0][:200]

    with psycopg.connect(db_url()) as conn, conn.cursor() as cur:
        if not forest_path.exists():
            cur.execute(
                "select payload from gridworks.messages where message_type_name=%s and persisted_at < %s "
                "and exists (select 1 from jsonb_array_elements(payload->'Nodes') n where n->>'Alias'=%s) "
                "order by persisted_at desc limit 1",
                (FOREST_TYPE, start, subtree))
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"no journaled {FOREST_TYPE} before {start} holding {subtree}")
            forest = restrict_forest(row[0], subtree)
            refused = decode(forest)
            if refused:
                raise SystemExit(f"restricted forest does not decode: {refused}")
            forest_path.write_text(json.dumps(forest, indent=1) + "\n")
            print(f"forest: wrote {forest_path.relative_to(UMBRELLA)} ({len(forest['Nodes'])} nodes)")
        else:
            print(f"forest: kept {forest_path.relative_to(UMBRELLA)}")

        cur.execute(
            "select persisted_at, from_alias, message_type_name, payload from gridworks.messages "
            "where persisted_at >= %s and persisted_at < %s and from_alias = any(%s) order by persisted_at, id",
            (start, end, senders))
        rows = cur.fetchall()

    counts: dict[tuple[str, str | None], int] = {}
    refusals: dict[tuple[str, str | None], int] = {}
    n_body = 0
    with (out / "messages.jsonl").open("w") as w:
        for persisted_at, frm, typ, payload in rows:
            rec: dict = {"t": iso(persisted_at), "from": frm, "type": typ, "body": None}
            if typ in bodies_for:
                rec["body"] = payload
                n_body += 1
                key = (typ, payload.get("Version"))
                counts[key] = counts.get(key, 0) + 1
                refused = decode(payload)
                if refused:
                    rec["refused"] = refused
                    refusals[key] = refusals.get(key, 0) + 1
            w.write(json.dumps(rec, separators=(",", ":")) + "\n")

    size_kb = (out / "messages.jsonl").stat().st_size // 1024
    print(f"messages: {len(rows)} rows, {n_body} with bodies, {size_kb} kB -> {out.relative_to(UMBRELLA)}/messages.jsonl")
    for key, n in sorted(counts.items()):
        print(f"  {key[0]}/{key[1]}: {n} decoded" + (f", {refusals[key]} refused" if key in refusals else ""))


if __name__ == "__main__":
    main()
