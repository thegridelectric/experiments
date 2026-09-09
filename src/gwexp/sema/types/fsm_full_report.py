from typing import Literal
from pydantic import ConfigDict
from gwexp.sema.base import SemaType
from gwexp.sema.property_format import SpaceheatName
from gwexp.sema.property_format import UUID4Str
from gwexp.sema.types.fsm_atomic_report import FsmAtomicReport


class FsmFullReport(SemaType):
    """Sema: https://schemas.electricity.works/types/fsm.full.report/001"""

    from_name: SpaceheatName
    trigger_id: UUID4Str
    atomic_list: list[FsmAtomicReport]
    type_name: Literal["fsm.full.report"] = "fsm.full.report"
    version: Literal["001"] = "001"

    model_config = ConfigDict(**(SemaType.model_config | {"extra": "allow"}))
