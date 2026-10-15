from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.enums import I2cMuxType
from gwexp.sema.property_format import NonNegativeInt
from gwexp.sema.property_format import PascalCase
from gwexp.sema.property_format import PositiveInt


class I2cMux(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.mux/000"""

    mux_name: PascalCase
    i2c_bus: PascalCase
    i2c_address: NonNegativeInt
    mux_type: I2cMuxType
    channels: PositiveInt
    type_name: Literal["i2c.mux"] = "i2c.mux"
    version: Literal["000"] = "000"
