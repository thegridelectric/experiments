from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.enums import I2cAdcChannel
from gwexp.sema.property_format import PositiveInt
from gwexp.sema.property_format import SpaceheatName


class I2cThermistorChannelConfig(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.channel.config/002"""

    channel_name: SpaceheatName
    adc_channel: I2cAdcChannel
    thermistor_beta: PositiveInt
    type_name: Literal["i2c.thermistor.channel.config"] = (
        "i2c.thermistor.channel.config"
    )
    version: Literal["002"] = "002"
