#!/usr/bin/env python3
"""Regenesis: recreate a registry's nodes from its latest forest snapshots.

One-off populate path for a fresh registry instance whose content lives in
the seed store as `g.node.forest` snapshots. Each snapshot is decoded through
the gnr sema snapshot (never read as a bare dict), the nodes are walked
parents-first, and every node is entered through the production operator
path — `gnr create` over the broker — so the registry applies it, answers
with its verdict, and the seed ear witnesses the new epoch. Nothing is
carried but identity: same GNodeId, alias, classes, display name; `Pending`;
no position point (create.cmd/001 forbids one).

Run inside the gnr venv so the snapshot classes and the `gnr` console script
resolve:  uv run --project ../../grid-node-registry python regenesis.py …
Broker / API / proof come from the environment `gnr create` already reads:
GNR_RABBIT__URL, GNR_API_BASE, GNR_WRITE_PROOF, GNR_BROKER_CA_FILE.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from gnr.sema.codec import default_codec
from gnr.sema.enums import GNodeStatus
from gnr.sema.types import GNodeForest, GNodeGt

ALREADY_EXISTS = "already exists"


class Outcome(NamedTuple):
    """One node's regenesis result: `verdict` is applied / exists / failed."""

    alias: str
    g_node_id: str
    verdict: str
    detail: str


def load_forest(path: Path) -> GNodeForest:
    """Decode one seed-store forest object; refuse anything that isn't one."""
    with path.open(encoding="utf-8") as f:
        decoded = default_codec.from_dict(json.load(f))
    assert isinstance(decoded, GNodeForest), f"{path}: not a g.node.forest"
    return decoded


def parents_first(forests: list[GNodeForest]) -> list[GNodeGt]:
    """Every node across the snapshots, ordered so each alias's parent (its
    dotted prefix) comes before it; roots first. Duplicate GNodeIds across
    snapshots are refused — per-root snapshots must not overlap."""
    seen: dict[str, GNodeGt] = {}
    for forest in forests:
        for node in forest.nodes:
            if node.g_node_id in seen:
                raise SystemExit(f"GNodeId {node.g_node_id} appears in two snapshots")
            seen[node.g_node_id] = node
    return sorted(seen.values(), key=lambda n: (n.alias.count("."), n.alias))


def create_command(node: GNodeGt) -> list[str]:
    return [
        "gnr",
        "create",
        node.alias,
        node.g_node_class,
        "--g-node-id",
        node.g_node_id,
        "--display-name",
        node.display_name,
    ]


def regenerate(node: GNodeGt, dry_run: bool) -> Outcome:
    cmd = create_command(node)
    if dry_run:
        return Outcome(node.alias, node.g_node_id, "dry-run", " ".join(cmd))
    # `gnr create` asks "ENTER to publish" (an empty line is the yes), then
    # for the write proof (empty when the target has no gate); both on stdin.
    answers = "\n" + os.environ.get("GNR_WRITE_PROOF", "") + "\n"
    run = subprocess.run(
        cmd, input=answers, text=True, capture_output=True, check=False
    )
    out = (run.stdout + run.stderr).strip()
    # The verdict lines are the ones gnr create marks; the rest is pika noise.
    marked = [
        ln
        for ln in out.splitlines()
        if ln.startswith(("✓", "✗")) or ALREADY_EXISTS in ln
    ]
    if run.returncode == 0:
        return Outcome(
            node.alias, node.g_node_id, "applied", marked[-1] if marked else ""
        )
    if ALREADY_EXISTS in out:
        return Outcome(
            node.alias, node.g_node_id, "exists", marked[-1] if marked else ""
        )
    return Outcome(node.alias, node.g_node_id, "failed", out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "forests",
        nargs="+",
        type=Path,
        help="seed-store g.node.forest objects, one per root (latest snapshot)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print, don't publish")
    args = parser.parse_args()

    forests = [load_forest(p) for p in args.forests]
    nodes = parents_first(forests)
    not_pending = [n.alias for n in nodes if n.status != GNodeStatus.Pending]
    if not_pending:
        raise SystemExit(
            f"regenesis carries Pending nodes only; not Pending: {not_pending}"
        )
    located = [n.alias for n in nodes if n.position_point_id is not None]
    if located:
        print(f"note: dropping position ids on {len(located)} nodes (pending-first)")

    print(f"{len(nodes)} nodes from {len(forests)} snapshot(s), parents-first")
    outcomes: list[Outcome] = []
    for node in nodes:
        outcome = regenerate(node, args.dry_run)
        outcomes.append(outcome)
        print(f"  {outcome.verdict:8} {outcome.alias}  {outcome.detail}")
        if outcome.verdict == "failed":
            break  # a parent that failed means every descendant would too

    counts = {
        v: sum(1 for o in outcomes if o.verdict == v)
        for v in ("applied", "exists", "failed")
    }
    print(
        f"applied {counts['applied']}  exists {counts['exists']}  failed {counts['failed']}"
    )
    sys.exit(1 if counts["failed"] else 0)


if __name__ == "__main__":
    main()
