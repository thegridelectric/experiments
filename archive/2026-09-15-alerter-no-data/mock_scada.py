"""A mocked scada for the NoData witness: publish a wrapped report.event
as one dev house on a cadence, go quiet, then resume.

Runs in the alerter's venv (gwbase, pika) with this repo's snapshot on
the path:

    PYTHONPATH=../src uv run --project ../../gridworks-alerter \
        python mock_scada.py --cadence 5 --talk 20 --quiet 60 --resume 20
"""

from __future__ import annotations

import argparse
import os
import time
import uuid

import pika
from gwbase.transport_encoding import TransportClass, WrappedRoutingEnvelope
from gwbase.wrapped import wrap_bytes
from gwexp.sema.property_format import (
    LeftRightDot,
    SpaceheatName,
    UTCMilliseconds,
    UUID4Str,
)
from gwexp.sema.types import ChannelReadings, Report, ReportEvent
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import TypeAdapter

LRD = TypeAdapter(LeftRightDot)
SH_NAME = TypeAdapter(SpaceheatName)
UUID4 = TypeAdapter(UUID4Str)

HOUSE: LeftRightDot = LRD.validate_python("d1.isone.me.versant.keene.spruce")
SCADA: LeftRightDot = LRD.validate_python(f"{HOUSE}.scada")
ALERTER: LeftRightDot = LRD.validate_python("d1.alerts")
CHANNEL: SpaceheatName = SH_NAME.validate_python("hp-idu-pwr")
INSTANCE_ID: UUID4Str = UUID4.validate_python(str(uuid.uuid4()))
SLOT_S = 300


def now_ms() -> UTCMilliseconds:
    return int(time.time() * 1000)


def report_event(read_ms: UTCMilliseconds) -> ReportEvent:
    """One channel, one reading, read now: built through the snapshot
    classes so the report's axioms validate before it goes on the wire."""
    report_id = UUID4.validate_python(str(uuid.uuid4()))
    slot_start_s = read_ms // 1000 - (read_ms // 1000) % SLOT_S
    report = Report(
        from_g_node_alias=SCADA,
        from_g_node_instance_id=INSTANCE_ID,
        about_g_node_alias=HOUSE,
        slot_start_unix_s=slot_start_s,
        slot_duration_s=SLOT_S,
        channel_reading_list=[
            ChannelReadings(
                channel_name=CHANNEL,
                value_list=[0],
                scada_read_time_unix_ms_list=[read_ms],
            )
        ],
        state_list=[],
        fsm_report_list=[],
        message_created_ms=read_ms,
        id=report_id,
    )
    return ReportEvent(
        message_id=report_id, time_created_ms=read_ms, src=SCADA, report=report
    )


def publish(channel: BlockingChannel) -> None:
    event = report_event(now_ms())
    envelope = WrappedRoutingEnvelope.from_classes(
        type_name=event.type_name,
        from_alias=SCADA,
        to_class=TransportClass.LeafTransactiveNode,
    )
    body = wrap_bytes(
        src=SCADA,
        dst=ALERTER,
        inner_type_name=event.type_name,
        inner_payload_dict=event.to_dict(),
    )
    channel.basic_publish("amq.topic", envelope.routing_key, body)
    print(f"{time.strftime('%H:%M:%S')} {event.type_name} from {SCADA}", flush=True)


def phase(
    channel: BlockingChannel, name: str, seconds: int, cadence: int, talking: bool
) -> None:
    print(f"{time.strftime('%H:%M:%S')} phase {name} for {seconds}s", flush=True)
    end = time.time() + seconds
    while time.time() < end:
        if talking:
            publish(channel)
        time.sleep(cadence if talking else 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cadence", type=int, default=5)
    parser.add_argument("--talk", type=int, default=20)
    parser.add_argument("--quiet", type=int, default=60)
    parser.add_argument("--resume", type=int, default=20)
    args = parser.parse_args()
    conn = pika.BlockingConnection(
        pika.URLParameters(os.environ["GWALERTER_RABBIT__URL"])
    )
    try:
        channel = conn.channel()
        phase(channel, "talk", args.talk, args.cadence, True)
        phase(channel, "quiet", args.quiet, args.cadence, False)
        phase(channel, "resume", args.resume, args.cadence, True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
