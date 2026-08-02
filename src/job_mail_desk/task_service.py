from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta

from .markdown_store import MarkdownTaskStore
from .models import JobTask, ParsedEvent
from .parser import SHANGHAI
from .privacy import redact_text


def _slug_hash(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def message_hash(message_id: str) -> str:
    return _slug_hash(message_id, 32)


def application_id(event: ParsedEvent) -> str:
    company = event.company or "unknown-company"
    role = event.role or "unknown-role"
    project = event.recruiting_project or "unknown-cycle"
    return _slug_hash(f"{company}|{role}|{project}", 20)


def task_id(event: ParsedEvent, app_id: str | None = None) -> str:
    app_id = app_id or application_id(event)
    round_label = event.round or "unspecified"
    return _slug_hash(f"{app_id}|{event.event_type}|{event.stage}|{round_label}", 24)


def _compatible(value: str | None, existing: str | None) -> bool:
    return not value or not existing or value == existing


def _project_scope(value: str | None) -> str | None:
    if not value:
        return None
    if "雷火事业群" in value:
        return "netease-leihuo"
    if "互娱事业群" in value:
        return "netease-interactive"
    return None


def _compatible_project(value: str | None, existing: str | None) -> bool:
    if not value or not existing:
        return True
    value_scope = _project_scope(value)
    existing_scope = _project_scope(existing)
    if value_scope or existing_scope:
        return value_scope == existing_scope
    return value == existing


def _merge_project(existing: str | None, incoming: str | None) -> str | None:
    if not incoming:
        return existing
    if not existing:
        return incoming
    old_scope = _project_scope(existing)
    new_scope = _project_scope(incoming)
    if old_scope and new_scope:
        if old_scope != new_scope:
            return existing
        return max((existing, incoming), key=len)
    if old_scope and not new_scope:
        return existing
    if new_scope and not old_scope:
        return incoming
    return incoming


def _resolve_application_id(
    event: ParsedEvent,
    store: MarkdownTaskStore,
) -> str:
    """Attach later-stage messages to a compatible ghost application."""
    candidates = [
        task
        for task in store.all()
        if task.company == (event.company or "公司待确认")
        and _compatible(event.role, task.role)
        and _compatible_project(event.recruiting_project, task.recruiting_project)
    ]
    if not candidates:
        return application_id(event)
    if not event.recruiting_project:
        scopes = {
            scope
            for task in candidates
            if (scope := _project_scope(task.recruiting_project))
        }
        if len(scopes) > 1:
            return application_id(event)
    candidates.sort(key=lambda task: task.received_at, reverse=True)
    return candidates[0].application_id


def critical_time(task: JobTask) -> datetime | None:
    if (
        task.start_at
        and task.end_at
        and task.end_at - task.start_at > timedelta(hours=12)
    ):
        return task.end_at
    return task.start_at or task.deadline_at


def _priority(event: ParsedEvent, now: datetime) -> str:
    target = event.start_at or event.deadline_at
    if (
        event.start_at
        and event.end_at
        and event.end_at - event.start_at > timedelta(hours=12)
    ):
        target = event.end_at
    if not target:
        return "high" if event.stage != "招聘通知" else "normal"
    delta = target - now
    if timedelta(0) <= delta <= timedelta(hours=24):
        return "urgent"
    if timedelta(0) <= delta <= timedelta(days=7):
        return "high"
    return "normal"


def _merge(existing: JobTask, event: ParsedEvent, now: datetime) -> JobTask:
    previous_event_type = existing.event_type
    existing.company = event.company or existing.company
    existing.role = event.role or existing.role
    existing.recruiting_project = _merge_project(
        existing.recruiting_project,
        event.recruiting_project,
    )
    existing.received_at = max(existing.received_at, event.source_received_at)
    existing.event_type = event.event_type
    existing.stage = event.stage
    existing.round = event.round or existing.round
    existing.start_at = event.start_at or existing.start_at
    existing.end_at = event.end_at or existing.end_at
    existing.deadline_at = event.deadline_at or existing.deadline_at
    existing.priority = _priority(event, now)  # type: ignore[assignment]
    existing.change_type = event.change_type
    existing.confidence = max(existing.confidence, event.confidence)
    existing.title = event.title
    existing.action_summary = event.action_summary
    existing.requirements = list(event.requirements) or existing.requirements
    existing.source_sender = event.source_sender
    existing.source_url = event.source_url or existing.source_url
    existing.updated_at = now
    has_schedule = bool(event.start_at or event.end_at or event.deadline_at)
    if event.change_type == "cancel":
        existing.status = "cancelled"
    elif event.event_type == "rejection":
        existing.status = "done"
    elif previous_event_type == "rejection" and event.event_type != "rejection":
        existing.status = "planned" if has_schedule else "needs_review"
    elif existing.status == "irrelevant":
        pass
    elif existing.status in {"cancelled", "expired"}:
        existing.status = "planned" if has_schedule else "needs_review"
    elif existing.status in {"new", "needs_review", "confirmed"} and has_schedule:
        existing.status = "planned"
    elif event.event_type == "application" and existing.status == "needs_review":
        existing.status = "confirmed"
    return existing


def task_from_event(
    event: ParsedEvent,
    store: MarkdownTaskStore,
    *,
    now: datetime | None = None,
) -> JobTask:
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    source_hash = message_hash(event.source_message_id)
    source_match = next(
        (
            task
            for task in store.all()
            if task.source_message_hash == source_hash
        ),
        None,
    )
    if source_match:
        return _merge(source_match, event, current)
    resolved_application_id = _resolve_application_id(event, store)
    identifier = task_id(event, resolved_application_id)
    existing = store.load(identifier)
    if existing:
        return _merge(existing, event, current)
    company = redact_text(event.company or "公司待确认")
    if event.change_type == "cancel":
        status = "cancelled"
    elif event.event_type == "rejection":
        status = "done"
    elif event.event_type == "application":
        status = "confirmed"
    else:
        status = (
            "planned"
            if event.start_at or event.end_at or event.deadline_at
            else "needs_review"
        )
    title = re.sub(r"\s+", " ", event.title).strip()
    return JobTask(
        id=identifier,
        application_id=resolved_application_id,
        company=company,
        role=event.role,
        recruiting_project=event.recruiting_project,
        event_type=event.event_type,
        stage=event.stage,
        round=event.round,
        received_at=event.source_received_at,
        start_at=event.start_at,
        end_at=event.end_at,
        deadline_at=event.deadline_at,
        priority=_priority(event, current),  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        change_type=event.change_type,
        source_message_hash=message_hash(event.source_message_id),
        research_status="not_queued",
        confidence=event.confidence,
        title=title,
        action_summary=event.action_summary,
        requirements=list(event.requirements),
        source_sender=event.source_sender,
        source_url=event.source_url,
        is_ghost=event.event_type != "application",
        updated_at=current,
    )


def _parse_optional_time(value: object) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def _manual_priority(
    start_at: datetime | None,
    deadline_at: datetime | None,
    now: datetime,
) -> str:
    target = start_at or deadline_at
    if not target:
        return "normal"
    delta = target - now
    if timedelta(0) <= delta <= timedelta(hours=24):
        return "urgent"
    if timedelta(0) <= delta <= timedelta(days=7):
        return "high"
    return "normal"


def create_manual_task(
    payload: dict[str, object],
    store: MarkdownTaskStore,
    *,
    now: datetime | None = None,
) -> JobTask:
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    company = redact_text(str(payload.get("company") or "个人待办"))[:80]
    role = redact_text(str(payload.get("role") or "")).strip()[:80] or None
    project = (
        redact_text(str(payload.get("recruiting_project") or "")).strip()[:80]
        or None
    )
    start = _parse_optional_time(payload.get("start_at"))
    end = _parse_optional_time(payload.get("end_at"))
    deadline = _parse_optional_time(payload.get("deadline_at"))
    if start and end and end <= start:
        raise ValueError("结束时间必须晚于开始时间")
    action = redact_text(
        str(payload.get("action_summary") or "处理这项求职待办")
    )[:240]
    stage = redact_text(str(payload.get("stage") or "自定义待办"))[:40]
    round_label = redact_text(str(payload.get("round") or "")).strip()[:30] or None
    app_id = _slug_hash(
        f"manual|{company}|{role or 'unknown'}|{project or 'personal'}",
        20,
    )
    event_day = (start or deadline).date() if start or deadline else None
    if event_day:
        for existing in store.all():
            existing_target = existing.start_at or existing.deadline_at
            if (
                existing.event_type == "manual"
                and existing.status not in {"cancelled", "irrelevant"}
                and existing.company.casefold() == company.casefold()
                and (existing.role or "").casefold() == (role or "").casefold()
                and existing.stage.casefold() == stage.casefold()
                and existing_target
                and existing_target.date() == event_day
            ):
                existing.recruiting_project = project
                existing.round = round_label
                existing.start_at = start
                existing.end_at = end
                existing.deadline_at = deadline
                existing.priority = _manual_priority(start, deadline, current)  # type: ignore[assignment]
                existing.status = "planned" if start or deadline else "needs_review"
                existing.change_type = "update"
                existing.title = action
                existing.action_summary = action
                existing.manual_notes = redact_text(
                    str(payload.get("manual_notes") or "")
                )[:2000]
                existing.updated_at = current
                store.save(existing)
                return existing
    task = JobTask(
        id=uuid.uuid4().hex[:24],
        application_id=app_id,
        company=company,
        role=role,
        recruiting_project=project,
        event_type="manual",
        stage=stage,
        round=round_label,
        received_at=current,
        start_at=start,
        end_at=end,
        deadline_at=deadline,
        priority=_manual_priority(start, deadline, current),  # type: ignore[arg-type]
        status="planned" if start or deadline else "needs_review",
        change_type="new",
        source_message_hash="manual",
        research_status="not_queued",
        confidence=1.0,
        title=action,
        action_summary=action,
        manual_notes=redact_text(str(payload.get("manual_notes") or ""))[:2000],
        is_ghost=False,
        updated_at=current,
    )
    store.save(task)
    return task


def edit_task_fields(
    task_id_value: str,
    payload: dict[str, object],
    store: MarkdownTaskStore,
) -> JobTask:
    task = store.load(task_id_value)
    if not task:
        raise KeyError(task_id_value)
    if "company" in payload:
        task.company = (
            redact_text(str(payload.get("company") or "个人待办"))[:80]
            or "个人待办"
        )
    for field_name, limit in (
        ("role", 80),
        ("recruiting_project", 80),
        ("round", 30),
    ):
        if field_name in payload:
            value = redact_text(str(payload.get(field_name) or "")).strip()[:limit]
            setattr(task, field_name, value or None)
    if "stage" in payload:
        task.stage = (
            redact_text(str(payload.get("stage") or "自定义待办"))[:40]
            or "自定义待办"
        )
    if "action_summary" in payload:
        task.action_summary = (
            redact_text(str(payload.get("action_summary") or "处理这项求职待办"))[
                :240
            ]
            or "处理这项求职待办"
        )
    if "manual_notes" in payload:
        task.manual_notes = redact_text(
            str(payload.get("manual_notes") or "")
        )[:2000]
    for field_name in ("start_at", "end_at", "deadline_at"):
        if field_name in payload:
            setattr(task, field_name, _parse_optional_time(payload[field_name]))
    if task.start_at and task.end_at and task.end_at <= task.start_at:
        raise ValueError("结束时间必须晚于开始时间")
    current = datetime.now(SHANGHAI)
    task.priority = _manual_priority(
        task.start_at,
        task.deadline_at,
        current,
    )  # type: ignore[assignment]
    task.updated_at = current
    task.change_type = "update"
    store.save(task)
    return task
