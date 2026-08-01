from __future__ import annotations

from pathlib import Path

from .config import DASHBOARD_FILE, TASKS_DIR, Settings
from .exporter import export_dashboard
from .markdown_store import MarkdownTaskStore
from .progress import export_progress
from .research import close_requests_for_task
from .task_service import critical_time, edit_task_fields


ALLOWED_STATUSES = {
    "needs_review",
    "confirmed",
    "planned",
    "done",
    "cancelled",
    "irrelevant",
}


def _summary(task) -> dict[str, object]:
    target = critical_time(task)
    return {
        "id": task.id,
        "company": task.company,
        "role": task.role,
        "stage": task.stage,
        "round": task.round,
        "status": task.status,
        "start_at": task.start_at.isoformat() if task.start_at else None,
        "end_at": task.end_at.isoformat() if task.end_at else None,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
        "critical_time": target.isoformat() if target else None,
        "action_summary": task.action_summary,
    }


def list_tasks(
    *,
    company: str = "",
    role: str = "",
    stage: str = "",
    include_irrelevant: bool = False,
    store: MarkdownTaskStore | None = None,
) -> list[dict[str, object]]:
    source = store or MarkdownTaskStore(TASKS_DIR)

    def matches(value: str | None, query: str) -> bool:
        return not query or query.casefold() in (value or "").casefold()

    tasks = [
        task
        for task in source.all()
        if (include_irrelevant or task.status != "irrelevant")
        and matches(task.company, company)
        and matches(task.role, role)
        and matches(task.stage, stage)
    ]
    tasks.sort(key=lambda item: (critical_time(item) is None, critical_time(item) or item.received_at))
    return [_summary(task) for task in tasks]


def sync_outputs(
    settings: Settings,
    store: MarkdownTaskStore,
    *,
    local_dashboard: Path = DASHBOARD_FILE,
) -> dict[str, object]:
    tasks = store.all()
    export_dashboard(tasks, local_dashboard, settings)
    outputs = {"local_dashboard": str(local_dashboard)}
    if settings.obsidian_enabled:
        export_dashboard(tasks, settings.obsidian_output, settings)
        outputs["obsidian"] = str(settings.obsidian_output)
    if settings.progress_enabled:
        export_progress(
            tasks,
            settings.progress_output,
            source_path=settings.progress_source,
        )
        outputs["progress"] = str(settings.progress_output)
    return {"task_count": len(tasks), "outputs": outputs}


def apply_task_update(
    settings: Settings,
    task_id: str,
    changes: dict[str, object],
    *,
    store: MarkdownTaskStore | None = None,
    local_dashboard: Path = DASHBOARD_FILE,
) -> dict[str, object]:
    changes = dict(changes)
    target_store = store or MarkdownTaskStore(TASKS_DIR)
    task = target_store.load(task_id)
    if not task:
        raise KeyError(f"未找到任务：{task_id}")
    status_value = str(changes.pop("status", "") or "").strip()
    editable = {
        key: value
        for key, value in changes.items()
        if key
        in {
            "company",
            "role",
            "recruiting_project",
            "stage",
            "round",
            "start_at",
            "end_at",
            "deadline_at",
            "action_summary",
            "manual_notes",
        }
    }
    if editable:
        task = edit_task_fields(task_id, editable, target_store)
    if status_value:
        if status_value not in ALLOWED_STATUSES:
            raise ValueError(f"不支持的状态：{status_value}")
        task = target_store.update_status(task_id, status_value)
        if status_value in {"done", "cancelled", "irrelevant"}:
            close_requests_for_task(
                settings.research_queue,
                task_id,
                reason=f"task_status:{status_value}",
            )
            task.research_status = "closed"
            target_store.save(task)
    synced = sync_outputs(settings, target_store, local_dashboard=local_dashboard)
    return {"task": _summary(task), **synced}
