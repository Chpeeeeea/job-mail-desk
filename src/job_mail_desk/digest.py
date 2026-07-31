from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .markdown_store import MarkdownTaskStore, _atomic_write
from .parser import SHANGHAI
from .task_service import critical_time


PERIOD_LABELS = {
    "morning": "早间",
    "noon": "午间",
    "evening": "晚间",
}


def generate_digest(
    period: str,
    store: MarkdownTaskStore,
    output_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    if period not in PERIOD_LABELS:
        raise ValueError(f"未知汇总时段：{period}")
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    tasks = store.all()
    active = [
        task
        for task in tasks
        if task.status not in {"done", "cancelled", "irrelevant"}
    ]
    today = [
        task
        for task in active
        if critical_time(task) and critical_time(task).date() == current.date()  # type: ignore[union-attr]
    ]
    week = [
        task
        for task in active
        if critical_time(task)
        and current <= critical_time(task) <= current + timedelta(days=7)  # type: ignore[operator]
    ]
    review = [task for task in active if critical_time(task) is None]
    path = output_dir / f"{current:%Y-%m-%d}.md"
    lines = [
        "---",
        f"title: {current:%Y-%m-%d} 求职邮件简报",
        "type: jobmaildesk-digest",
        f"updated: {current.isoformat()}",
        "---",
        "",
        f"# {current:%Y-%m-%d} {PERIOD_LABELS[period]}求职简报",
        "",
        f"> 生成时间：{current:%Y-%m-%d %H:%M}",
        "",
        "## 今日重点",
        "",
    ]
    lines.extend(
        [f"- [ ] {task.company}｜{task.stage}｜{task.action_summary}" for task in today]
        or ["_暂无_"]
    )
    lines.extend(["", "## 未来 7 天", ""])
    lines.extend(
        [f"- {task.company}｜{task.stage}｜{critical_time(task):%m-%d %H:%M}" for task in week]
        or ["_暂无_"]
    )
    lines.extend(["", "## 待确认时间", ""])
    lines.extend(
        [f"- {task.company}｜{task.stage}｜{task.action_summary}" for task in review]
        or ["_暂无_"]
    )
    lines.extend(
        [
            "",
            "## 事实边界",
            "",
            "- 本简报来自本地结构化邮件信息，不包含完整邮件正文。",
            "- 网络经验研究需要单独核验，不能替代企业官方通知。",
            "",
        ]
    )
    _atomic_write(path, "\n".join(lines))
    return path
