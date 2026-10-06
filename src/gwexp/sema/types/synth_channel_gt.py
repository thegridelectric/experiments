from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.enums import SpaceheatTelemetryName
from gwexp.sema.property_format import LeftRightDot
from gwexp.sema.property_format import PositiveInt
from gwexp.sema.property_format import SpaceheatName
from gwexp.sema.property_format import UUID4Str


class SynthChannelGt(SemaType):
    """Sema: https://schemas.electricity.works/types/synth.channel.gt/000"""

    id: UUID4Str
    name: SpaceheatName
    created_by_node_name: SpaceheatName
    telemetry_name: SpaceheatTelemetryName
    terminal_asset_alias: LeftRightDot
    strategy: str
    display_name: str
    sync_report_minutes: PositiveInt
    type_name: Literal["synth.channel.gt"] = "synth.channel.gt"
    version: Literal["000"] = "000"
