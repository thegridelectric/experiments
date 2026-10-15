from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.enums import GpioSenseMode
from gwexp.sema.property_format import PascalCase
from gwexp.sema.property_format import UUID4Str


class GpioSensorComponentGt(SemaType):
    """Sema: https://schemas.electricity.works/types/gpio.sensor.component.gt/000"""

    component_id: UUID4Str
    board_component_id: UUID4Str
    gpio_name: PascalCase
    sense_mode: GpioSenseMode
    display_name: str | None = None
    hw_uid: str | None = None
    type_name: Literal["gpio.sensor.component.gt"] = "gpio.sensor.component.gt"
    version: Literal["000"] = "000"
