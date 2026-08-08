from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

from .application_registry import ApplicationRegistry
from .config import (
    APPLICATIONS_DIR,
    DASHBOARD_CACHE,
    RESEARCH_QUEUE,
    STATE_DB,
    TASKS_DIR,
    UNRESOLVED_DIR,
)
from .markdown_store import MarkdownTaskStore, _atomic_write
from .models import JobTask
from .parser import SHANGHAI
from .progress import progress_payload
from .research import request_states
from .state import StateStore
from .task_service import critical_time
from .unresolved_store import UnresolvedStore


DASHBOARD_CACHE_SCHEMA = 4


def _view(task: JobTask, now: datetime) -> str:
    if task.status in {"done", "expired", "cancelled"}:
        return "progress"
    if (
        task.status == "confirmed"
        and task.event_type == "application"
        and not critical_time(task)
    ):
        return "progress"
    if task.snoozed_until and task.snoozed_until > now:
        return "snoozed"
    target = critical_time(task)
    if not target:
        return "review"
    if target.date() == now.date() or target <= now + timedelta(hours=24):
        return "today"
    return "week"


def _task_payload(
    task: JobTask,
    now: datetime,
    research_state: dict[str, object] | None = None,
) -> dict[str, object]:
    target = critical_time(task)
    remaining = None
    if target:
        seconds = int((target - now).total_seconds())
        if seconds < 0:
            remaining = "已过时间"
        elif seconds < 3600:
            remaining = f"{max(1, seconds // 60)} 分钟"
        elif seconds < 86400:
            remaining = f"{seconds // 3600} 小时"
        else:
            remaining = f"{seconds // 86400} 天"
    queue_status = str((research_state or {}).get("status") or "")
    research_status = {
        "pending": "queued",
        "running": "running",
        "completed": "completed",
        "blocked": "blocked",
        "closed": "closed",
    }.get(queue_status, task.research_status)
    result_path = str((research_state or {}).get("result_path") or "")
    todo_visible = task.status == "done" or (
        task.status in {"confirmed", "planned"}
        and (bool(target) or task.event_type == "manual")
    )
    return {
        "id": task.id,
        "application_id": task.application_id,
        "application_key": task.application_key,
        "company": task.company,
        "role": task.role or "岗位待确认",
        "event_type": task.event_type,
        "received_at": task.received_at.isoformat(),
        "project": task.recruiting_project or "",
        "stage": task.stage,
        "round": task.round or "",
        "time": target.isoformat() if target else None,
        "start_at": task.start_at.isoformat() if task.start_at else None,
        "end_at": task.end_at.isoformat() if task.end_at else None,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "completed_at_inferred": task.completed_at_inferred,
        "snoozed_until": (
            task.snoozed_until.isoformat() if task.snoozed_until else None
        ),
        "time_label": target.astimezone(SHANGHAI).strftime("%m-%d %H:%M")
        if target
        else "时间待确认",
        "remaining": remaining,
        "action": task.action_summary,
        "manual_notes": task.manual_notes,
        "status": task.status,
        "priority": task.priority,
        "research_status": research_status,
        "research_result_path": result_path,
        "has_source": bool(task.source_url),
        "actionable": todo_visible,
        "view": _view(task, now),
    }


def dashboard_payload(
    research_queue: Path = RESEARCH_QUEUE,
    progress_source: Path | None = None,
) -> dict[str, object]:
    now = datetime.now(SHANGHAI)
    all_tasks = MarkdownTaskStore(TASKS_DIR).all()
    tasks = [
        task
        for task in all_tasks
        if task.status not in {"cancelled", "expired", "irrelevant"}
    ]
    states = request_states(research_queue)
    payload = [_task_payload(task, now, states.get(task.id)) for task in tasks]
    progress = progress_payload(all_tasks, progress_source)
    application_views: dict[str, dict[str, object]] = {}
    for application in progress:
        for key in (
            application.get("application_id"),
            application.get("application_key"),
            application.get("legacy_application_id"),
        ):
            if key:
                application_views[str(key)] = application
    for item in payload:
        application = application_views.get(str(item.get("application_key") or ""))
        if not application:
            application = application_views.get(str(item.get("application_id") or ""))
        if not application:
            continue
        item["company"] = application.get("company") or item["company"]
        item["role"] = application.get("role") or item["role"]
        if application.get("active") is False:
            item["view"] = "progress"
            item["actionable"] = False
    registry = ApplicationRegistry(APPLICATIONS_DIR)
    unresolved: list[dict[str, object]] = []
    for record in UnresolvedStore(UNRESOLVED_DIR).all():
        if record.status != "pending":
            continue
        candidates = []
        for key in record.candidate_application_keys:
            application = registry.load(key)
            if application:
                candidates.append(
                    {
                        "application_key": key,
                        "company": application.company,
                        "role": application.role or "岗位待确认",
                    }
                )
        target = record.deadline_at or record.end_at or record.start_at
        unresolved.append(
            {
                **record.to_dict(),
                "attention_type": "unresolved_identity",
                "candidates": candidates,
                "time": target.isoformat() if target else None,
                "time_label": target.astimezone(SHANGHAI).strftime("%m-%d %H:%M")
                if target
                else "时间待确认",
            }
        )
    payload.sort(
        key=lambda item: (
            item["status"] == "done",
            item["time"] is None,
            item["time"] or "9999",
        )
    )
    return {
        "generated_at": now.isoformat(),
        "tasks": payload,
        "unresolved": unresolved,
        "progress": progress,
        "counts": {
            "today": sum(
                item["view"] == "today" and item["status"] != "done"
                for item in payload
            ),
            "week": sum(
                item["view"] == "week" and item["status"] != "done"
                for item in payload
            ),
            "review": sum(
                item["view"] == "review" and item["status"] != "done"
                for item in payload
            ) + len(unresolved),
            "list": sum(
                item["status"] != "done" and bool(item["actionable"])
                for item in payload
            ),
            "progress": len(progress),
            "research": sum(
                item["research_status"] in {"queued", "running", "blocked"}
                or bool(item["research_result_path"])
                for item in payload
            ),
        },
        "health": StateStore(STATE_DB).health(),
    }


def _source_signature(
    research_queue: Path,
    progress_source: Path | None,
) -> list[list[object]]:
    paths = list(sorted(TASKS_DIR.glob("*.md")))
    paths.extend(sorted(UNRESOLVED_DIR.glob("*.md")))
    paths.extend([research_queue, STATE_DB])
    if progress_source:
        paths.append(progress_source)
    signature: list[list[object]] = [
        ["schema", DASHBOARD_CACHE_SCHEMA],
        ["minute", datetime.now(SHANGHAI).strftime("%Y-%m-%dT%H:%M")]
    ]
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            signature.append([str(path), 0, 0])
        else:
            signature.append([str(path), stat.st_mtime_ns, stat.st_size])
    return signature


def cached_dashboard_payload(
    research_queue: Path = RESEARCH_QUEUE,
    progress_source: Path | None = None,
    cache_path: Path = DASHBOARD_CACHE,
) -> dict[str, object]:
    """Return a persisted local snapshot when its Markdown inputs are unchanged."""
    signature = _source_signature(research_queue, progress_source)
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("signature") == signature and isinstance(cached.get("payload"), dict):
            return cached["payload"]
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    payload = dashboard_payload(research_queue, progress_source)
    signature = _source_signature(research_queue, progress_source)
    _atomic_write(
        cache_path,
        json.dumps(
            {"signature": signature, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    return payload
