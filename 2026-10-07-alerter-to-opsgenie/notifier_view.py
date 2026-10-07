"""What the notifier holds for the alerts an alerter raised, read off an
Opsgenie listing (`GET /v2/alerts?query=source:<alias>`), as typed
records: the facts the protocol checks (open or closed, how many times
Opsgenie folded a create into the same alias, who closed it), not
Opsgenie's intake shape.

No sema word yet carries Opsgenie's alert as its API returns it; the
`NotifierAlertView` record stands in and retires when that word exists
(candidate `atl.opsgenie.alert`, GridWorks-owned under the vendor's
prefix like `hubitat.*`, versioned by us as their API moves). Dict form
appears once, at the boundary.

    uv run python notifier_view.py evidence/<date>/opsgenie-resolved.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gwexp.sema.property_format import UTCMilliseconds, UUID4Str  # noqa: E402

UTC_MS = TypeAdapter(UTCMilliseconds)
ALERT_ID = TypeAdapter(UUID4Str)


class NotifierAlertView(NamedTuple):
    """One alert as the notifier holds it. `alert_id` is the alias the tap
    gave it (the `gw.alert` `AlertId`); `status` is the notifier's `open`
    or `closed`; `count` how many creates the notifier folded into this
    alias; `created_ms` when the notifier first took it; `closed_by` who
    closed it, None while open; `message` the headline the tap sent."""

    alert_id: UUID4Str
    status: str
    count: int
    created_ms: UTCMilliseconds
    closed_by: str | None
    message: str


def from_listing(listing: dict) -> list[NotifierAlertView]:
    """The views in an Opsgenie listing response, in its order."""
    views: list[NotifierAlertView] = []
    for alert in listing["data"]:
        created = datetime.fromisoformat(alert["createdAt"].replace("Z", "+00:00"))
        views.append(
            NotifierAlertView(
                alert_id=ALERT_ID.validate_python(alert["alias"]),
                status=alert["status"],
                count=int(alert["count"]),
                created_ms=UTC_MS.validate_python(int(created.timestamp() * 1000)),
                closed_by=alert.get("report", {}).get("closedBy"),
                message=alert["message"],
            )
        )
    return views


def line(view: NotifierAlertView) -> str:
    closed = f" closed by {view.closed_by}" if view.closed_by else ""
    return (
        f"{view.status} {view.alert_id} count={view.count} "
        f"created={datetime.fromtimestamp(view.created_ms / 1000).astimezone().isoformat(timespec='seconds')}"
        f"{closed} | {view.message}"
    )


if __name__ == "__main__":
    for view in from_listing(json.loads(Path(sys.argv[1]).read_text())):
        print(line(view))
