#!/usr/bin/env python3
"""Print the window's evidence from the scada's own report events in
instances/: every state change of the relays and valves named below, each
pico-cycler FsmFullReport with its TriggerId, and the secondary-flow series
at the pico's cadence. Decodes through gwsproto (ReportEvent), so the
evidence is read as sema instances, never as dicts.

Run with the scada venv (gwsproto is not in the experiments env):

    ../../gridworks-scada/gw_spaceheat/venv/bin/python extract_window.py
"""
import glob
import os
from datetime import datetime, timedelta, timezone

from gwsproto.named_types.events import ReportEvent

ET = timezone(timedelta(hours=-4))
NODES = ("secondary-pump-relay", "iso-valve-relay", "vdc-relay", "pico-cycler")
FLOW_CHANNEL = "secondary-flow"
HERE = os.path.dirname(os.path.abspath(__file__))


def et(unix_ms: int) -> str:
    return datetime.fromtimestamp(unix_ms / 1000, ET).strftime("%H:%M:%S")


for path in sorted(glob.glob(os.path.join(HERE, "instances", "*-report.event-*.json"))):
    with open(path) as f:
        event = ReportEvent.model_validate_json(f.read())
    report = event.Report
    print(f"== {os.path.basename(path)}  slot {et(report.SlotStartUnixS * 1000)}")
    for machine in report.StateList:
        node = machine.MachineHandle.split(".")[-1]
        if node in NODES:
            rows = ", ".join(f"{et(t)} {s}" for t, s in zip(machine.UnixMsList, machine.StateList))
            print(f"  {node}: {rows}")
    for fsm in report.FsmReportList:
        steps = " -> ".join(f"{a.ToState}@{et(a.UnixTimeMs)}" for a in fsm.AtomicList)
        print(f"  fsm {fsm.FromName} trigger {fsm.TriggerId[:8]}: {steps}")
    for channel in report.ChannelReadingList:
        if channel.ChannelName == FLOW_CHANNEL:
            series = ", ".join(
                f"{et(t)} {v / 100:.2f}" for t, v in zip(channel.ScadaReadTimeUnixMsList, channel.ValueList)
            )
            print(f"  {FLOW_CHANNEL} (gpm): {series}")
