from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.enums import I2cAdcType
from gwexp.sema.property_format import NonNegativeInt
from gwexp.sema.property_format import PascalCase
from gwexp.sema.property_format import PositiveFloat
from gwexp.sema.property_format import PositiveInt


class I2cCtInterfaceCapability(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.ct.interface.capability/000"""

    name: PascalCase
    i2c_bus: PascalCase
    i2c_address: NonNegativeInt
    adc_type: I2cAdcType
    adc_reference_volts: PositiveFloat
    channels: PositiveInt
    type_name: Literal["i2c.ct.interface.capability"] = "i2c.ct.interface.capability"
    version: Literal["000"] = "000"
