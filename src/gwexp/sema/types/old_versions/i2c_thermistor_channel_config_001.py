from typing import Literal
from pydantic import StrictInt
from gwexp.sema.base import SemaType
from gwexp.sema.enums import I2cAdcChannel
from gwexp.sema.enums import SpaceheatUnit
from gwexp.sema.property_format import PositiveInt
from gwexp.sema.property_format import SpaceheatName
from gwexp.sema.types.i2c_thermistor_channel_config import I2cThermistorChannelConfig


class I2cThermistorChannelConfig001(SemaType):
    """Sema: https://schemas.electricity.works/types/i2c.thermistor.channel.config/001"""

    channel_name: SpaceheatName
    poll_period_ms: PositiveInt | None = None
    capture_period_s: PositiveInt
    async_capture: bool
    async_capture_delta: PositiveInt | None = None
    exponent: StrictInt
    unit: SpaceheatUnit
    adc_channel: I2cAdcChannel
    send_to_derived: bool
    thermistor_beta: PositiveInt
    type_name: Literal["i2c.thermistor.channel.config"] = (
        "i2c.thermistor.channel.config"
    )
    version: Literal["001"] = "001"

    def upgrade(self) -> I2cThermistorChannelConfig:
        """
        - Unit: drop (redundant; unit and scaling are carried by channel identity)
        - Exponent: drop (redundant; unit and scaling are carried by channel identity)
        - CapturePeriodS / AsyncCapture / AsyncCaptureDelta / PollPeriodMs: drop
          (capture/report tuning moved to operational-params capture.tuning)
        - SendToDerived: drop (derived routing is computed from DerivedChannel
          InputChannelNames)
        """
        data = self.model_dump()
        del data["unit"]
        del data["exponent"]
        for key in (
            "capture_period_s",
            "async_capture",
            "async_capture_delta",
            "poll_period_ms",
            "send_to_derived",
        ):
            data.pop(key, None)
        data["version"] = "002"
        return I2cThermistorChannelConfig.model_validate(data)
