from typing import Literal
from pydantic import BaseModel, ConfigDict
from gwexp.sema.base import SemaType
from gwexp.sema.types.gridworks_header import GridworksHeader


class Payload(BaseModel):
    model_config = ConfigDict(
        alias_generator=SemaType.model_config.get("alias_generator"),
        populate_by_name=True,
        extra="allow",
    )

    type_name: str


class Gw(SemaType):
    """Sema: https://schemas.electricity.works/types/gw"""

    header: GridworksHeader
    payload: Payload
    type_name: Literal["gw"] = "gw"
