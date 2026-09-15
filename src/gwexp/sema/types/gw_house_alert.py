from typing import Literal
from pydantic import model_validator
from gwexp.sema.base import SemaType
from gwexp.sema.enums import GwHouseAlertKind
from gwexp.sema.property_format import LeftRightDot
from gwexp.sema.property_format import UTCMilliseconds
from gwexp.sema.property_format import UUID4Str
from gwexp.sema.types.channel_readings import ChannelReadings


class GwHouseAlert(SemaType):
    """Sema: https://schemas.electricity.works/types/gw.house.alert/000"""

    src: LeftRightDot
    about_g_node_alias: LeftRightDot
    kind: GwHouseAlertKind
    alert_id: UUID4Str
    raised_ms: UTCMilliseconds
    summary: str
    evidence: list[ChannelReadings]
    type_name: Literal["gw.house.alert"] = "gw.house.alert"
    version: Literal["000"] = "000"

    @model_validator(mode="after")
    def check_axiom_1(self) -> "GwHouseAlert":
        """
        Axiom 1: TerminalAssetAliasConstraint
        AboutGNodeAlias SHALL identify a TerminalAsset and therefore SHALL end with the suffix
        ".ta".
        """
        if not self.about_g_node_alias.endswith(".ta"):
            raise ValueError(
                f'TerminalAssetAliasConstraint: AboutGNodeAlias ({self.about_g_node_alias}) does not end with the suffix ".ta".'
            )
        return self
