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
ApplicationStatus = Literal["active", "ended", "archived"]


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
    application_key: str | None = None
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
            application_key=(
                str(payload["application_key"])
                if payload.get("application_key")
                else None
            ),
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


@dataclass
class ApplicationRecord:
    application_key: str
    company_key: str
    company: str
    recruiting_project: str | None
    recruiting_year: int | None
    business_unit: str | None
    role: str | None
    role_aliases: list[str]
    job_code: str | None
    submitted_at: datetime | None
    status: ApplicationStatus
    source: str
    confirmed_by_user: bool
    identity_locked: bool
    legacy_application_ids: list[str] = field(default_factory=list)
    identity_evidence: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: int = 1
    rule_version: str = "identity-registry-v1"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for name in ("submitted_at", "created_at", "updated_at"):
            value = payload[name]
            payload[name] = value.isoformat() if value else None
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ApplicationRecord":
        def parse_time(name: str) -> datetime | None:
            value = payload.get(name)
            return datetime.fromisoformat(str(value)) if value else None

        def parse_bool(name: str, default: bool = False) -> bool:
            value = payload.get(name, default)
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
            return value

        def parse_string_list(name: str) -> list[str]:
            value = payload.get(name, [])
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"{name} must be a list of strings")
            return list(value)

        year = payload.get("recruiting_year")
        if isinstance(year, bool):
            raise ValueError("recruiting_year must be an integer year or null")
        if year not in {None, ""}:
            try:
                parsed_year = int(year)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "recruiting_year must be an integer year or null"
                ) from exc
            if not 2000 <= parsed_year <= 2100:
                raise ValueError("recruiting_year must be between 2000 and 2100")
        else:
            parsed_year = None
        status = str(payload.get("status") or "active")
        if status not in {"active", "ended", "archived"}:
            raise ValueError("invalid application status")
        schema_version = payload.get("schema_version", 1)
        if not isinstance(schema_version, int) or schema_version != 1:
            raise ValueError("unsupported application schema_version")
        return cls(
            application_key=str(payload["application_key"]),
            company_key=str(payload.get("company_key") or "unknown-company"),
            company=str(payload.get("company") or "公司待确认"),
            recruiting_project=(
                str(payload["recruiting_project"])
                if payload.get("recruiting_project")
                else None
            ),
            recruiting_year=parsed_year,
            business_unit=(
                str(payload["business_unit"])
                if payload.get("business_unit")
                else None
            ),
            role=str(payload["role"]) if payload.get("role") else None,
            role_aliases=parse_string_list("role_aliases"),
            job_code=str(payload["job_code"]) if payload.get("job_code") else None,
            submitted_at=parse_time("submitted_at"),
            status=status,  # type: ignore[arg-type]
            source=str(payload.get("source") or "unknown"),
            confirmed_by_user=parse_bool("confirmed_by_user"),
            identity_locked=parse_bool("identity_locked"),
            legacy_application_ids=parse_string_list("legacy_application_ids"),
            identity_evidence=parse_string_list("identity_evidence"),
            created_at=parse_time("created_at"),
            updated_at=parse_time("updated_at"),
            schema_version=schema_version,
            rule_version=str(
                payload.get("rule_version") or "identity-registry-v1"
            ),
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
