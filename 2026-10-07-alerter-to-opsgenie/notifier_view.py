"""What the notifier holds for the alerts an alerter raised, read off an
Opsgenie listing (`GET /v2/alerts?query=source:<alias>`) into
`gw.opsgenie.alert` words: the facts the protocol checks (open or
closed, how many times Opsgenie folded a create into the same alias,
who closed it), not Opsgenie's intake shape. The dict form of Opsgenie's
response appears once, here, at the boundary.

    uv run python notifier_view.py evidence/<date>/opsgenie-resolved.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gwexp.sema.enums import GwOpsgenieAlertStatus, GwOpsgeniePriority  # noqa: E402
from gwexp.sema.types import GwOpsgenieAlert  # noqa: E402

STATUS = {"open": GwOpsgenieAlertStatus.Open, "closed": GwOpsgenieAlertStatus.Closed}


def stamp_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def from_listing(listing: dict) -> list[GwOpsgenieAlert]:
    """The words in an Opsgenie listing response, in its order."""
    words: list[GwOpsgenieAlert] = []
    for alert in listing["data"]:
        report = alert.get("report", {})
        words.append(
            GwOpsgenieAlert(
                alias=alert["alias"],
                opsgenie_id=alert["id"],
                tiny_id=alert["tinyId"],
                message=alert["message"],
                status=STATUS[alert["status"]],
                acknowledged=bool(alert["acknowledged"]),
                count=int(alert["count"]),
                priority=GwOpsgeniePriority(alert["priority"]),
                source=alert["source"],
                tags=list(alert["tags"]),
                created_ms=stamp_ms(alert["createdAt"]),
                last_occurred_ms=stamp_ms(alert["lastOccurredAt"]),
                acknowledged_by=report.get("acknowledgedBy"),
                closed_by=report.get("closedBy"),
            )
        )
    return words


def line(word: GwOpsgenieAlert) -> str:
    closed = f" closed by {word.closed_by}" if word.closed_by else ""
    created = datetime.fromtimestamp(word.created_ms / 1000).astimezone()
    return (
        f"{word.status.value.lower()} {word.alias} count={word.count} "
        f"created={created.isoformat(timespec='seconds')}{closed} | {word.message}"
    )


if __name__ == "__main__":
    for word in from_listing(json.loads(Path(sys.argv[1]).read_text())):
        print(line(word))
