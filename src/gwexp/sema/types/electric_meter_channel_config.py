from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.property_format import SpaceheatName
from gwexp.sema.types.egauge_register_config import EgaugeRegisterConfig


class ElectricMeterChannelConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/electric.meter.channel.config/000"""

    channel_name: SpaceheatName
    egauge_register_config: EgaugeRegisterConfig | None = None
    type_name: Literal["electric.meter.channel.config"] = (
        "electric.meter.channel.config"
    )
    version: Literal["000"] = "000"
