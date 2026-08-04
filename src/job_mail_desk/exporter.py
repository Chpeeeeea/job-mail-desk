from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from .config import Settings
from .markdown_store import MarkdownTaskStore, _atomic_write
from .models import JobTask
from .parser import SHANGHAI
from .privacy import redact_text, sanitized_url
from .task_service import critical_time


MANAGED_START = "<!-- jobmaildesk:managed-start -->"
MANAGED_END = "<!-- jobmaildesk:managed-end -->"
CHECKED_PATTERN = re.compile(
    r"^- \[(?P<state>[ xX])\].*?<!-- jobmaildesk:(?P<id>[0-9a-f]{24}) -->",
    re.MULTILINE,
)


def import_checked_states(path: Path, store: MarkdownTaskStore) -> int:
    if not path.exists():
        return 0
    content = path.read_text(encoding="utf-8")
    updates = 0
    for match in CHECKED_PATTERN.finditer(content):
        task = store.load(match.group("id"))
        if not task:
            continue
        if task.status in {"cancelled", "irrelevant"}:
            continue
        if match.group("state").lower() == "x":
            desired = "done"
        elif task.status == "done":
            desired = "planned" if critical_time(task) else "needs_review"
        else:
            # An unchecked Markdown task means "not done"; it does not carry
            # enough information to downgrade confirmed application progress.
            continue
        if desired != task.status:
            store.update_status(task.id, desired)
            updates += 1
    return updates


def _time_label(task: JobTask) -> str:
    if task.start_at:
        start = task.start_at.astimezone(SHANGHAI)
        if task.end_at:
            end = task.end_at.astimezone(SHANGHAI)
            if start.date() == end.date():
                return f"{start:%Y-%m-%d %H:%M}–{end:%H:%M}"
            return f"{start:%Y-%m-%d %H:%M}–{end:%Y-%m-%d %H:%M}"
        return f"{start:%Y-%m-%d %H:%M}"
    if task.deadline_at:
        return f"{task.deadline_at.astimezone(SHANGHAI):%Y-%m-%d %H:%M} 前"
    return "时间待确认"


def _bucket(task: JobTask, now: datetime) -> str:
    if task.status == "done":
        return "done"
    if task.status == "cancelled":
        return "cancelled"
    target = critical_time(task)
    if target is None:
        return "review"
    if task.start_at and task.end_at and task.start_at <= now < task.end_at:
        return "urgent"
    delta = target.astimezone(SHANGHAI) - now
    if delta < timedelta(0):
        return "expired"
    if delta <= timedelta(hours=24):
        return "urgent"
    if delta <= timedelta(days=7):
        return "week"
    return "later"


def _task_lines(task: JobTask, settings: Settings) -> list[str]:
    state = "x" if task.status == "done" else " "
    target = critical_time(task)
    due = f" 📅 {target:%Y-%m-%d}" if target else ""
    round_label = f"｜{task.round}" if task.round else ""
    role = f"｜{task.role}" if task.role else ""
    action = redact_text(task.action_summary)
    if "你好" in action or "您好" in action or len(action) > 160:
        action = f"请核对{task.stage}通知并处理下一步。"
    lines = [
        (
            f"- [{state}] **{_time_label(task)}**｜{task.company}{role}｜"
            f"{task.stage}{round_label}｜{action}{due} "
            f"<!-- jobmaildesk:{task.id} -->"
        )
    ]
    if settings.include_sender and task.source_sender:
        lines.append(f"  - 来源：{redact_text(task.source_sender)}")
    if settings.include_private_links and task.source_url:
        safe_url = sanitized_url(task.source_url, remove_all_query=False)
        if safe_url:
            lines.append(f"  - [打开通知链接]({safe_url})")
    return lines


def _section(title: str, tasks: list[JobTask], settings: Settings) -> list[str]:
    lines = [f"## {title}", ""]
    if not tasks:
        return lines + ["_暂无_", ""]
    for task in tasks:
        lines.extend(_task_lines(task, settings))
        lines.append("")
    return lines


def export_dashboard(
    tasks: list[JobTask],
    output: Path,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    existing = output.read_text(encoding="utf-8") if output.exists() else ""
    if MANAGED_START in existing and MANAGED_END in existing:
        prefix, remainder = existing.split(MANAGED_START, 1)
        _, suffix = remainder.split(MANAGED_END, 1)
        prefix = re.sub(
            r"(?m)^updated: .*$",
            f"updated: {current:%Y-%m-%d %H:%M}",
            prefix,
            count=1,
        )
    else:
        prefix = (
            "---\n"
            "title: 求职硬截止待办集\n"
            "type: todo-dashboard\n"
            "status: active\n"
            f"updated: {current:%Y-%m-%d %H:%M}\n"
            "tags: [求职, 待办, 硬截止]\n"
            "---\n\n"
            "# 求职硬截止待办集\n\n"
            "> 由 JobMailDesk 本地只读提取。请人工核对时间；"
            "本页不保存授权码或完整邮件正文。\n\n"
        )
        suffix = (
            "\n## 手动补充\n\n"
            "<!-- 可在这里添加自己的待办；自动更新不会覆盖本区。 -->\n"
        )
    buckets = {key: [] for key in ("urgent", "week", "later", "review", "done")}
    for task in sorted(
        [
            item
            for item in tasks
            if item.status not in {"cancelled", "expired", "irrelevant"}
            and not (
                item.event_type == "application"
                and item.status == "confirmed"
                and critical_time(item) is None
            )
        ],
        key=lambda item: (
            critical_time(item) is None,
            critical_time(item) or item.received_at,
        ),
    ):
        buckets[_bucket(task, current)].append(task)
    lines = [MANAGED_START, ""]
    for key, title in (
        ("urgent", "紧急：24 小时内"),
        ("week", "未来 7 天"),
        ("later", "更晚安排"),
        ("review", "待确认时间"),
        ("done", "已完成"),
    ):
        lines.extend(_section(title, buckets[key], settings))
    lines.append(MANAGED_END)
    content = prefix.rstrip() + "\n\n" + "\n".join(lines) + "\n" + suffix.lstrip()
    _atomic_write(output, content)
    return len(tasks)
