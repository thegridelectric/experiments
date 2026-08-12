#!/usr/bin/env python3
"""Bounded real-hardware boot of the unlimbo scada — the spruce window rung.

Runs ON THE SPRUCE PI with the unlimbo checkout's venv, everything else on
the bus stopped (deployed scada + its restart watchdog + the summer hack):

    cd ~/gridworks-scada-unlimbo/gw_spaceheat && \
        venv/bin/python ~/window_boot.py [seconds]

Environment comes from ~/envs/dev.env: real spruce (hw1) identity, dev
broker only via the laptop's ssh -R 1885 tunnel, experiment artifact paths
(~/.config/gridworks/scada-experiment/). The app is built through the BASE
`App.make_app_for_cli` (mkdirs + logging + TLS check + instantiate), not
ScadaApp's override — the override adds the universe guardrail, which
rightly refuses an hw1 identity on a localhost broker at real boots; this
bounded harness is the guardrail's designed test-boot exemption
(credential-structural isolation: the env file carries no hw1 creds).

The run is bounded by asyncio.wait_for, so the window self-terminates even
on a dropped connection; the i2c evidence (read sequences, readback gate,
errors) lands in the boot log, the per-sample zone series on the dev
broker (spruce-async1 ops artifact: every polled sample trips async
capture).
"""

import asyncio
import sys
from pathlib import Path

SCADA_GW = Path("~/gridworks-scada-unlimbo/gw_spaceheat").expanduser()
sys.path.insert(0, str(SCADA_GW))

from gwproactor.app import App  # noqa: E402
from scada_app import ScadaApp  # noqa: E402

DEFAULT_ENV = Path("~/envs/dev.env").expanduser()
DEFAULT_SECONDS = 420  # >= 5 min of 1 Hz reads inside the window, plus boot

# The window's own paths root. NOT overridable from the env file, and not
# even by a get_settings(paths_name=...) argument: every app-construction
# path re-applies cls.paths_name() (get_settings ends with
# .with_paths(name=... or cls.paths_name()), and make_app_for_cli rebuilds
# settings through cls()). The 2026-08-12 window leaked its dying shutdown
# event to prod through the shared event dir that way. The ONLY reliable
# override is the classmethod itself — hence the subclass — and the boot
# ASSERTS the isolation on the app's own settings before running.
PATHS_NAME = "scada-experiment"


class WindowScadaApp(ScadaApp):
    @classmethod
    def paths_name(cls) -> str:
        return PATHS_NAME


def build_app(env_file: Path) -> ScadaApp:
    settings = WindowScadaApp.get_settings(env_file=env_file)
    app = App.make_app_for_cli.__func__(  # base impl: no universe assert
        WindowScadaApp, app_settings=settings, env_file=env_file
    )
    for isolated in (app.settings.paths.event_dir, app.settings.paths.log_dir):
        if PATHS_NAME not in str(isolated):
            raise SystemExit(
                f"paths-root isolation failed: {isolated} is outside the "
                f"{PATHS_NAME} root — refusing to run (events/logs would "
                "share the deployed scada's dirs and reupload to prod)"
            )
    return app


async def _run_bounded(app: ScadaApp, seconds: int) -> None:
    try:
        await asyncio.wait_for(app.proactor.run_forever(), timeout=seconds)
    except asyncio.TimeoutError:
        app.proactor.stop()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    seconds = int(argv[0]) if argv else DEFAULT_SECONDS
    env_file = Path(argv[1]).expanduser() if len(argv) > 1 else DEFAULT_ENV
    app = build_app(env_file)
    layout = app.hardware_layout
    print(
        f"== window boot: {layout.scada_g_node_alias} for {seconds}s, "
        f"broker {app.settings.gridworks_mqtt.host}:"
        f"{app.settings.gridworks_mqtt.port} ==",
        flush=True,  # stdout is block-buffered under redirection
    )
    asyncio.run(_run_bounded(app, seconds))
    vals = dict(app.scada._data.latest_channel_values)
    zone_gw = {
        k: v for k, v in vals.items()
        if k.startswith("zone") and ("-gw-temp" in k or "-gw-microvolts" in k)
    }
    non_null = {k: v for k, v in zone_gw.items() if v is not None}
    print(f"== window done: {len(non_null)}/{len(zone_gw)} zone gw channels populated ==")
    for k in sorted(non_null):
        print(f"  {k} = {non_null[k]}")
    return 0 if len(non_null) == len(zone_gw) and zone_gw else 1


if __name__ == "__main__":
    raise SystemExit(main())
