from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal


ChangeType = Literal["new", "update", "cancel"]
TaskStatus = Literal[
    "new",
    "needs_review",
    "confirmed",
    "planned",
    "done",
    "cancelled",
    "expired",
    "irrelevant",
]
Priority = Literal["urgent", "high", "normal", "low"]


@dataclass(frozen=True)
class MailRecord:
    uid: str
    subject: str
    message_id: str
    sender: str
    received_at: datetime
    body: str


@dataclass(frozen=True)
class ParsedEvent:
    company: str | None
    role: str | None
    recruiting_project: str | None
    event_type: str
    stage: str
    round: str | None
    title: str
    start_at: datetime | None
    end_at: datetime | None
    deadline_at: datetime | None
    source_message_id: str
    source_received_at: datetime
    source_sender: str
    source_url: str | None
    action_summary: str
    requirements: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    confidence: float
    change_type: ChangeType


@dataclass
class JobTask:
    id: str
    application_id: str
    company: str
    role: str | None
    recruiting_project: str | None
    event_type: str
    stage: str
    round: str | None
    received_at: datetime
    start_at: datetime | None
    end_at: datetime | None
    deadline_at: datetime | None
    priority: Priority
    status: TaskStatus
    change_type: ChangeType
    source_message_hash: str
    research_status: str
    confidence: float
    title: str
    action_summary: str
    requirements: list[str] = field(default_factory=list)
    manual_notes: str = ""
    source_sender: str | None = None
    source_url: str | None = None
    is_ghost: bool = False
    snoozed_until: datetime | None = None
    completed_at: datetime | None = None
    completed_at_inferred: bool = False
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for name in (
            "received_at",
            "start_at",
            "end_at",
            "deadline_at",
            "snoozed_until",
            "completed_at",
            "updated_at",
        ):
            value = payload[name]
            payload[name] = value.isoformat() if value else None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "JobTask":
        def parse_time(name: str) -> datetime | None:
            value = payload.get(name)
            return datetime.fromisoformat(str(value)) if value else None

        return cls(
            id=str(payload["id"]),
            application_id=str(payload["application_id"]),
            company=str(payload.get("company") or "公司待确认"),
            role=str(payload["role"]) if payload.get("role") else None,
            recruiting_project=(
                str(payload["recruiting_project"])
                if payload.get("recruiting_project")
                else None
            ),
            event_type=str(payload.get("event_type") or "notice"),
            stage=str(payload.get("stage") or "招聘通知"),
            round=str(payload["round"]) if payload.get("round") else None,
            received_at=parse_time("received_at"),  # type: ignore[arg-type]
            start_at=parse_time("start_at"),
            end_at=parse_time("end_at"),
            deadline_at=parse_time("deadline_at"),
            priority=str(payload.get("priority") or "normal"),  # type: ignore[arg-type]
            status=str(payload.get("status") or "needs_review"),  # type: ignore[arg-type]
            change_type=str(payload.get("change_type") or "new"),  # type: ignore[arg-type]
            source_message_hash=str(payload.get("source_message_hash") or ""),
            research_status=str(payload.get("research_status") or "not_queued"),
            confidence=float(payload.get("confidence") or 0),
            title=str(payload.get("title") or ""),
            action_summary=str(payload.get("action_summary") or ""),
            requirements=list(payload.get("requirements") or []),  # type: ignore[arg-type]
            manual_notes=str(payload.get("manual_notes") or ""),
            source_sender=(
                str(payload["source_sender"]) if payload.get("source_sender") else None
            ),
            source_url=(
                str(payload["source_url"]) if payload.get("source_url") else None
            ),
            is_ghost=bool(payload.get("is_ghost", False)),
            snoozed_until=parse_time("snoozed_until"),
            completed_at=parse_time("completed_at"),
            completed_at_inferred=bool(payload.get("completed_at_inferred", False)),
            updated_at=parse_time("updated_at"),
        )


@dataclass(frozen=True)
class ResearchRequest:
    id: str
    task_id: str
    company: str
    role: str | None
    recruiting_project: str | None
    year: int | None
    stage: str
    topics: tuple[str, ...]
    created_at: datetime
    status: str = "pending"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["topics"] = list(self.topics)
        payload["created_at"] = self.created_at.isoformat()
        return payload
