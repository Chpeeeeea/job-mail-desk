from __future__ import annotations

from datetime import datetime, timedelta

from .config import STATE_DB, TASKS_DIR
from .markdown_store import MarkdownTaskStore
from .models import JobTask
from .parser import SHANGHAI
from .state import StateStore
from .task_service import critical_time


def _view(task: JobTask, now: datetime) -> str:
    target = critical_time(task)
    if not target:
        return "review"
    if target.date() == now.date() or target <= now + timedelta(hours=24):
        return "today"
    return "week"


def _task_payload(task: JobTask, now: datetime) -> dict[str, object]:
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
    return {
        "id": task.id,
        "application_id": task.application_id,
        "company": task.company,
        "role": task.role or "岗位待确认",
        "project": task.recruiting_project or "",
        "stage": task.stage,
        "round": task.round or "",
        "time": target.isoformat() if target else None,
        "start_at": task.start_at.isoformat() if task.start_at else None,
        "end_at": task.end_at.isoformat() if task.end_at else None,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "time_label": target.astimezone(SHANGHAI).strftime("%m-%d %H:%M")
        if target
        else "时间待确认",
        "remaining": remaining,
        "action": task.action_summary,
        "manual_notes": task.manual_notes,
        "status": task.status,
        "priority": task.priority,
        "research_status": task.research_status,
        "view": _view(task, now),
    }


def dashboard_payload() -> dict[str, object]:
    now = datetime.now(SHANGHAI)
    tasks = [
        task
        for task in MarkdownTaskStore(TASKS_DIR).all()
        if task.status not in {"done", "cancelled", "irrelevant"}
    ]
    payload = [_task_payload(task, now) for task in tasks]
    payload.sort(
        key=lambda item: (
            item["time"] is None,
            item["time"] or "9999",
        )
    )
    return {
        "generated_at": now.isoformat(),
        "tasks": payload,
        "counts": {
            "today": sum(item["view"] == "today" for item in payload),
            "week": sum(item["view"] == "week" for item in payload),
            "review": sum(item["view"] == "review" for item in payload),
            "research": sum(
                item["research_status"] not in {"not_queued", "completed"}
                for item in payload
            ),
        },
        "health": StateStore(STATE_DB).health(),
    }
