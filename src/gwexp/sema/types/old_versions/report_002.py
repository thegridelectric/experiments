from typing import Literal
from gwexp.sema.base import SemaType
from gwexp.sema.property_format import LeftRightDot
from gwexp.sema.property_format import PositiveInt
from gwexp.sema.property_format import UTCMilliseconds
from gwexp.sema.property_format import UTCSeconds
from gwexp.sema.property_format import UUID4Str
from gwexp.sema.types.channel_readings import ChannelReadings
from gwexp.sema.types.fsm_full_report import FsmFullReport
from gwexp.sema.types.machine_states import MachineStates
from gwexp.sema.types.old_versions.fsm_full_report_000 import FsmFullReport000
from gwexp.sema.types.report import Report


class Report002(SemaType):
    """Sema: https://schemas.electricity.works/types/report/002"""

    from_g_node_alias: LeftRightDot
    from_g_node_instance_id: UUID4Str
    about_g_node_alias: LeftRightDot
    slot_start_unix_s: UTCSeconds
    slot_duration_s: PositiveInt
    channel_reading_list: list[ChannelReadings]
    state_list: list[MachineStates]
    fsm_report_list: list[FsmFullReport000 | FsmFullReport]
    message_created_ms: UTCMilliseconds
    id: UUID4Str
    type_name: Literal["report"] = "report"
    version: str = "002"

    def upgrade(self) -> Report:
        """- FsmReportList[]: fsm.full.report:000 -> 001"""
        data = self.model_dump()
        data["fsm_report_list"] = [
            fsm_report.upgrade() if fsm_report.version == "000" else fsm_report
            for fsm_report in self.fsm_report_list
        ]
        data["version"] = "003"
        return Report.model_validate(data)
