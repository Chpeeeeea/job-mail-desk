from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

from .models import JobTask


FRONTMATTER = "---"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def render_task(task: JobTask) -> str:
    payload = task.to_dict()
    frontmatter = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    checkbox = "x" if task.status == "done" else " "
    time_bits = []
    if task.start_at:
        time_bits.append(f"开始：{task.start_at:%Y-%m-%d %H:%M}")
    if task.end_at:
        time_bits.append(f"结束：{task.end_at:%Y-%m-%d %H:%M}")
    if task.deadline_at:
        time_bits.append(f"截止：{task.deadline_at:%Y-%m-%d %H:%M}")
    requirements = (
        "\n".join(f"- {item}" for item in task.requirements)
        if task.requirements
        else "- 暂无结构化要求，请人工核对原邮件。"
    )
    source_link = (
        f"[在本机打开通知链接]({task.source_url})"
        if task.source_url
        else "无可用链接"
    )
    return (
        f"{FRONTMATTER}\n{frontmatter}\n{FRONTMATTER}\n\n"
        f"# {task.company}｜{task.stage}\n\n"
        f"- [{checkbox}] {task.action_summary} <!-- jobmaildesk:{task.id} -->\n\n"
        "## 内容摘要\n\n"
        f"{task.title}\n\n"
        "## 下一步行动\n\n"
        f"{task.action_summary}\n\n"
        "## 时间与提醒\n\n"
        + ("\n".join(f"- {item}" for item in time_bits) if time_bits else "- 时间待确认")
        + "\n\n## 邮件要求\n\n"
        + requirements
        + "\n\n## 本地通知链接\n\n"
        + source_link
        + "\n\n## 研究进度\n\n"
        + f"- 状态：{task.research_status}\n\n"
        + "## 手动补充\n\n"
        + (task.manual_notes or "_暂无_")
        + "\n\n"
        + "## 来源与事实边界\n\n"
        + "- 邮件原文未落盘；本页只保存结构化字段和脱敏摘要。\n"
        + "- 网络经验只能作为准备参考，不等同于本人真题或企业官方事实。\n"
    )


def parse_task(path: Path) -> JobTask:
    content = path.read_text(encoding="utf-8")
    if not content.startswith(f"{FRONTMATTER}\n"):
        raise ValueError(f"任务文件缺少 frontmatter：{path}")
    _, frontmatter, _ = content.split(FRONTMATTER, maxsplit=2)
    payload = yaml.safe_load(frontmatter) or {}
    task = JobTask.from_dict(payload)
    marker = f"<!-- jobmaildesk:{task.id} -->"
    if marker in content:
        line = next((item for item in content.splitlines() if marker in item), "")
        if "- [x]" in line.lower():
            task.status = "done"
    return task


class MarkdownTaskStore:
    def __init__(self, tasks_dir: Path) -> None:
        self.tasks_dir = tasks_dir
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.md"

    def save(self, task: JobTask) -> Path:
        task.updated_at = task.updated_at or datetime.now().astimezone()
        path = self.path_for(task.id)
        _atomic_write(path, render_task(task))
        return path

    def load(self, task_id: str) -> JobTask | None:
        path = self.path_for(task_id)
        return parse_task(path) if path.exists() else None

    def all(self) -> list[JobTask]:
        tasks = []
        for path in sorted(self.tasks_dir.glob("*.md")):
            try:
                tasks.append(parse_task(path))
            except (KeyError, TypeError, ValueError, yaml.YAMLError):
                continue
        return tasks

    def update_status(
        self,
        task_id: str,
        status: str,
        snoozed_until: datetime | None = None,
    ) -> JobTask:
        task = self.load(task_id)
        if task is None:
            raise KeyError(task_id)
        task.status = status  # type: ignore[assignment]
        task.snoozed_until = snoozed_until
        task.updated_at = datetime.now().astimezone()
        self.save(task)
        return task
