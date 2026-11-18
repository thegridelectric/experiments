"""Builds, once, the bruce transition matrices a house's FLO requests need,
into bruce's cache under BRUCE_BASE_PATH. The FLO refuses a plant shape
with no cached matrix rather than build one in the request path, so this
runs before the FLO serves the house.

Each request is the FLO's sample flo.params set to the house: its bruce
tuning from the operational params and its store from the hardware
layout, in each seasonal storage mode: AllTanks models every store tank
and BufferOnly one.
bruce keys a matrix on the tuning, the store volume and the longest step,
so the sample's prices and forecasts do not reach the key.

Run in the FLO image, with CAN_COMPUTE_TRANSITION_MATRICES=true:

    python flo_matrix.py <house folder>
"""

import json
import resource
import sys
import time
from pathlib import Path

import gwflo
from bruce.graph_optimizer.assets.heat_pump_water_tank.asset import (
    HeatPumpWaterTankAsset,
)
from bruce.graph_optimizer.transitions_matrix import get_transition_matrix
from bruce.sema.enums import SeasonalStorageMode
from bruce.sema.types import FloParams, FloTuningBruce
from bruce.service import params_from_request

SAMPLE = Path(gwflo.__file__).parent / "sema" / "samples" / "flo.params.001.json"


def water_store(layout: dict) -> dict:
    """The layout's gw.water.store, read by hand: the FLO image carries no
    gw.house0.layout word."""
    store = layout["Hydronic"]["WaterStore"]
    assert store["TypeName"] == "gw.water.store"
    return store


def request(
    tuning: FloTuningBruce, mode: SeasonalStorageMode, store: dict
) -> FloParams:
    sample = json.loads(SAMPLE.read_text())
    tanks = store["TotalStoreTanks"] if mode is SeasonalStorageMode.AllTanks else 1
    sensors = tanks * store["TempSensorsPerTank"]
    sample.update(
        SeasonalStorageMode=mode.value,
        TanksModeled=tanks,
        GallonsPerTank=store["GallonsPerTank"],
        TempSensorsPerTank=store["TempSensorsPerTank"],
        InitialThermocline1=min(sample["InitialThermocline1"], sensors),
        InitialThermocline2=min(sample["InitialThermocline2"], sensors),
        Tuning=tuning.to_dict(),
    )
    return FloParams.from_dict(sample)


def main() -> None:
    house = Path(sys.argv[1])
    ops = json.loads((house / "operational-params.json").read_text())
    tuning = FloTuningBruce.from_dict(ops["FloTuning"])
    store = water_store(json.loads((house / "hardware-layout.json").read_text()))
    for mode in SeasonalStorageMode:
        start = time.monotonic()
        asset = HeatPumpWaterTankAsset(params_from_request(request(tuning, mode, store)))
        matrix = get_transition_matrix(asset)
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(
            f"{mode.value}: "
            f"{asset.transition_matrix_params().cache_filename(asset.name)} "
            f"shape {matrix.shape} in {time.monotonic() - start:.0f} s, "
            f"peak {peak_mb:.0f} MB",
            flush=True,
        )


if __name__ == "__main__":
    main()
