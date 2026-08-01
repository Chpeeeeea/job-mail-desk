from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .markdown_store import MarkdownTaskStore, _atomic_write
from .models import JobTask, ResearchRequest
from .privacy import contains_sensitive_public_data, safe_public_terms


RESEARCH_STAGES = {
    "在线笔试",
    "人才测评",
    "AI 面试",
    "HR 面试",
    "面试",
}


def build_request(task: JobTask, now: datetime | None = None) -> ResearchRequest | None:
    if task.stage not in RESEARCH_STAGES or task.company == "公司待确认":
        return None
    created = (now or datetime.now().astimezone()).replace(microsecond=0)
    year = None
    for value in (task.recruiting_project, task.title):
        if value:
            digits = "".join(character for character in value if character.isdigit())
            if len(digits) >= 4:
                year = int(digits[:4])
                break
    safe = safe_public_terms(
        task.company,
        task.role,
        task.recruiting_project,
        task.stage,
    )
    if not safe:
        return None
    identifier = hashlib.sha256(
        f"{task.id}|{'|'.join(safe)}".encode("utf-8")
    ).hexdigest()[:24]
    return ResearchRequest(
        id=identifier,
        task_id=task.id,
        company=task.company,
        role=task.role,
        recruiting_project=task.recruiting_project,
        year=year,
        stage=task.stage,
        topics=("招聘流程", "面经", "问题汇总", "准备建议"),
        created_at=created,
    )


def queue_request(
    request: ResearchRequest,
    path: Path,
    store: MarkdownTaskStore | None = None,
) -> bool:
    payload = request.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)
    if contains_sensitive_public_data(serialized):
        raise ValueError("研究请求包含不允许公开的敏感字段。")
    existing_ids: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                existing_ids.add(str(json.loads(line).get("id")))
            except json.JSONDecodeError:
                continue
    if request.id in existing_ids:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized + "\n")
    if store:
        task = store.load(request.task_id)
        if task:
            task.research_status = "queued"
            store.save(task)
    return True


def pending_requests(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    results = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("status") == "pending":
            results.append(payload)
    return results


def request_states(path: Path) -> dict[str, dict[str, object]]:
    """Return the latest persisted research state for each task."""
    if not path.exists():
        return {}
    states: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = str(payload.get("task_id") or "")
        if task_id:
            states[task_id] = payload
    return states


def close_requests_for_task(
    path: Path,
    task_id: str,
    *,
    reason: str,
) -> int:
    if not path.exists():
        return 0
    changed = 0
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue
        if payload.get("task_id") == task_id and payload.get("status") in {
            "pending",
            "blocked",
        }:
            payload["status"] = "closed"
            payload["reason"] = reason
            payload["updated_at"] = datetime.now().astimezone().replace(
                microsecond=0
            ).isoformat()
            changed += 1
        lines.append(json.dumps(payload, ensure_ascii=False))
    if changed:
        _atomic_write(path, "\n".join(lines) + "\n")
    return changed


def synchronize_research_state(
    tasks: list[JobTask],
    path: Path,
    store: MarkdownTaskStore,
) -> int:
    changed = 0
    for task in tasks:
        if task.status not in {"done", "cancelled", "irrelevant"}:
            continue
        closed = close_requests_for_task(
            path,
            task.id,
            reason=f"task_status:{task.status}",
        )
        if closed or task.research_status not in {"closed", "completed"}:
            task.research_status = "closed"
            store.save(task)
        changed += closed
    return changed
