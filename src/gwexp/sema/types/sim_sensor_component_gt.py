from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.property_format import PascalCase
from gwexp.sema.property_format import UUID4Str


class SimSensorComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/sim.sensor.component.gt/000"""

    component_id: UUID4Str
    device_type: PascalCase
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["sim.sensor.component.gt"] = "sim.sensor.component.gt"
    version: Literal["000"] = "000"
