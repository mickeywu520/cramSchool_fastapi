"""Punch clock schemas - mirror Rust receiver GcpPunchEvent (tolerant)."""

from pydantic import BaseModel, Field


class PunchDevice(BaseModel):
    maker: str = "SOYAL"
    model: str = "AR837EF"
    node_id: int = 1
    ip: str = ""
    source_sub_code: int | None = None

    model_config = {"extra": "ignore"}


class PunchEventInfo(BaseModel):
    function_code: int = 11
    event_code: str = "M11"
    description: str = ""
    door_no: int | None = None

    model_config = {"extra": "ignore"}


class PunchCard(BaseModel):
    uid_hex: str = ""
    uid_decimal: int | None = None
    card_number_hi: int | None = None
    card_number_lo: int | None = None
    # 向後相容別名 (PRD §5.2 預留, receiver 未來可能改送這些)
    site_code: int | None = None
    card_code: int | None = None

    model_config = {"extra": "ignore", "populate_by_name": True}


class PunchPerson(BaseModel):
    alias: str | None = None
    user_id: str | None = None

    model_config = {"extra": "ignore"}


class PunchType(BaseModel):
    punch_type: str = "unknown"
    duty_code: int | None = None
    duty_label: str | None = None

    model_config = {"extra": "ignore"}


class PunchIngestedBy(BaseModel):
    receiver_id: str = ""

    model_config = {"extra": "ignore"}


class GcpPunchEvent(BaseModel):
    schema_version: str = "v1"
    event_id: str
    message_type: str = "punch_event"
    occurred_at: str
    received_at: str | None = None
    device: PunchDevice = Field(default_factory=PunchDevice)
    event: PunchEventInfo = Field(default_factory=PunchEventInfo)
    card: PunchCard
    person: PunchPerson | None = None
    punch: PunchType | None = None
    ingested_by: PunchIngestedBy | None = None
    raw_message: str = ""

    model_config = {"extra": "ignore"}


class PunchIngestRequest(BaseModel):
    events: list[GcpPunchEvent]

    model_config = {"extra": "ignore"}


class PunchIngestItemResult(BaseModel):
    event_id: str
    status: str  # ok | duplicate | unknown_card | inactive | error
    student_id: int | None = None
    student_name: str | None = None


class PunchIngestResponse(BaseModel):
    received: int
    stored: int
    results: list[PunchIngestItemResult]


class AttendanceDailyResponse(BaseModel):
    student_id: int
    student_name: str
    card_number: str | None = None
    punch_date: str
    first_punch: str | None = None
    last_punch: str | None = None
    punch_count: int = 0

    model_config = {"from_attributes": True}
