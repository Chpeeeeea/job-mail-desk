from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
from pathlib import Path
import re

from .markdown_store import _atomic_write
from .models import JobTask
from .parser import SHANGHAI
from .privacy import redact_text
from .task_service import critical_time


MANAGED_START = "<!-- jobmaildesk:progress-start -->"
MANAGED_END = "<!-- jobmaildesk:progress-end -->"


def create_progress_template(path: Path) -> bool:
    """Create a user-maintained progress ledger without importing fake examples."""
    if path.exists() and path.stat().st_size:
        return False
    today = datetime.now(SHANGHAI).date().isoformat()
    content = f"""---
title: 求职进展台账
type: jobmaildesk-progress-source
created: {today}
updated: {today}
---

# 求职进展台账

> 每行使用：公司｜岗位｜当前进展｜下一步动作。JobMailDesk只读取下方“已投递或已进入流程”区域，不覆盖你的手写内容。

## 当前进展

### 已投递或已进入流程

<!-- 示例：- [x] 示例公司｜产品经理｜**一面已确认**｜8月6日14:00参加面试 -->

### 当前优先待投

<!-- 可自由记录尚未投递的岗位；这一部分不会自动进入求职进展卡片。 -->

## 状态约定

- `[x]`：已经投递或进入流程。
- 当前进展建议使用：已投递、测评、笔试、一面、二面、群面、Offer、未通过、已结束。
- 同一岗位进展变化时更新原行，不要重复追加相同岗位。
"""
    _atomic_write(path, content)
    return True


def _event_time(task: JobTask) -> datetime:
    return (
        critical_time(task)
        or task.updated_at
        or task.received_at
    ).astimezone(SHANGHAI)


def _status_label(status: str) -> str:
    return {
        "new": "新增",
        "needs_review": "待确认",
        "confirmed": "已确认",
        "planned": "已安排",
        "done": "已完成",
        "cancelled": "已取消",
        "expired": "已过期",
    }.get(status, status)


def _company_key(value: str) -> str:
    cleaned = re.sub(r"[\s（）()【】\[\]]+", "", value).casefold()
    cleaned = re.sub(r"(?:校园招聘|校招)$", "", cleaned)
    return {
        "deeproute.ai": "元戎启行",
        "深圳元戎启行科技有限公司": "元戎启行",
    }.get(cleaned, cleaned)


def _ledger_entries(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    marker = "### 已投递或已进入流程"
    if marker not in content:
        return []
    section = content.split(marker, 1)[1]
    section = section.split("\n### ", 1)[0]
    entries: list[dict[str, str]] = []
    for line in section.splitlines():
        if not re.match(r"^- \[[ xX]\] ", line):
            continue
        fields = [
            re.sub(r"[*_`]", "", item).strip()
            for item in line.split("] ", 1)[1].split("｜")
        ]
        if len(fields) < 3:
            continue
        entries.append(
            {
                "company": fields[0],
                "role": fields[1],
                "status": fields[2],
                "action": "｜".join(fields[3:]).strip(),
            }
        )
    return entries


def progress_payload(
    tasks: list[JobTask],
    source_path: Path | None = None,
) -> list[dict[str, object]]:
    """Build application-chain progress without actionable-list filtering."""
    grouped: dict[str, list[JobTask]] = defaultdict(list)
    for task in tasks:
        if task.status != "irrelevant":
            grouped[task.application_id].append(task)

    applications: list[dict[str, object]] = []
    for app_id, chain in grouped.items():
        chain.sort(key=_event_time)
        active = [
            item
            for item in chain
            if item.status not in {"done", "cancelled", "expired", "irrelevant"}
        ]
        current = active[-1] if active else chain[-1]
        company = next(
            (
                item.company
                for item in reversed(chain)
                if item.company not in {"公司待确认", "个人待办"}
            ),
            current.company,
        )
        role = next((item.role for item in reversed(chain) if item.role), None)
        project = next(
            (item.recruiting_project for item in reversed(chain) if item.recruiting_project),
            None,
        )
        applications.append(
            {
                "application_id": app_id,
                "company": company,
                "role": role or "岗位待确认",
                "project": project or "",
                "current_stage": current.stage,
                "current_round": current.round or "",
                "current_status": current.status,
                "status_label": _status_label(current.status),
                "active": bool(active),
                "next_time": (
                    critical_time(current).isoformat()
                    if critical_time(current) and critical_time(current) >= datetime.now(SHANGHAI)
                    else None
                ),
                "updated_at": _event_time(current).isoformat(),
                "history": [
                    {
                        "task_id": item.id,
                        "stage": item.stage,
                        "round": item.round or "",
                        "status": item.status,
                        "status_label": _status_label(item.status),
                        "time": critical_time(item).isoformat()
                        if critical_time(item)
                        else None,
                        "action": item.action_summary,
                    }
                    for item in reversed(chain)
                ],
            }
        )

    task_applications = list(applications)
    ledger_keys: set[tuple[str, str]] = set()
    task_states: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        task_states[_company_key(task.company)].add(task.status)
    for entry in _ledger_entries(source_path):
        company_key = _company_key(entry["company"])
        task_matches = [
            application
            for application in task_applications
            if _company_key(str(application["company"])) == company_key
        ]
        if task_matches:
            for application in task_matches:
                application["ledger_status"] = entry["status"]
                application["ledger_action"] = entry["action"]
            continue
        if task_states.get(company_key) == {"irrelevant"}:
            continue
        ledger_key = (company_key, re.sub(r"\s+", "", entry["role"]).casefold())
        if ledger_key in ledger_keys:
            continue
        ended = any(
            label in entry["status"]
            for label in ("已结束", "未通过", "撤回", "关闭")
        )
        identifier = hashlib.sha256(
            f"ledger|{entry['company']}|{entry['role']}".encode("utf-8")
        ).hexdigest()[:20]
        applications.append(
            {
                "application_id": identifier,
                "company": entry["company"],
                "role": entry["role"],
                "project": "",
                "current_stage": entry["status"],
                "current_round": "",
                "current_status": "done" if ended else "tracked",
                "status_label": entry["status"],
                "active": not ended,
                "next_time": None,
                "updated_at": "",
                "ledger_status": entry["status"],
                "ledger_action": entry["action"],
                "history": [
                    {
                        "task_id": None,
                        "stage": entry["status"],
                        "round": "",
                        "status": "done" if ended else "tracked",
                        "status_label": "决策台账",
                        "time": None,
                        "action": entry["action"],
                    }
                ],
            }
        )
        ledger_keys.add(ledger_key)
    applications.sort(
        key=lambda item: (
            not bool(item["active"]),
            item["next_time"] is None,
            item["next_time"] or "9999",
            str(item["company"]),
        )
    )
    return applications


def export_progress(
    tasks: list[JobTask],
    output: Path,
    *,
    now: datetime | None = None,
    source_path: Path | None = None,
) -> int:
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    applications = progress_payload(tasks, source_path)
    existing = output.read_text(encoding="utf-8") if output.exists() else ""
    if MANAGED_START in existing and MANAGED_END in existing:
        prefix, remainder = existing.split(MANAGED_START, 1)
        _, suffix = remainder.split(MANAGED_END, 1)
    else:
        prefix = (
            "---\n"
            "title: 求职当前进展\n"
            "type: job-progress\n"
            "status: active\n"
            "tags: [求职, 投递跟踪, 进展]\n"
            "---\n\n"
            "# 求职当前进展\n\n"
            "> 由 JobMailDesk 根据本地结构化任务生成。这里记录申请链；"
            "可执行时间仍以桌面待办和官方通知为准。\n\n"
            "关联入口：[[岗位投递决策台账]]\n\n"
        )
        suffix = (
            "\n## 手动补充\n\n"
            "<!-- 本区可手写复盘或决策；自动刷新不会覆盖。 -->\n"
        )

    active_count = sum(bool(item["active"]) for item in applications)
    lines = [
        MANAGED_START,
        "",
        f"> 更新时间：{current:%Y-%m-%d %H:%M}｜进行中 {active_count}｜申请链 {len(applications)}",
        "",
    ]
    if not applications:
        lines.extend(["_暂无流程记录_", ""])
    for application in applications:
        company = redact_text(str(application["company"]))
        role = redact_text(str(application["role"]))
        project = redact_text(str(application["project"]))
        heading = f"## {company}｜{role}"
        if project:
            heading += f"｜{project}"
        current_round = (
            f"｜{application['current_round']}"
            if application["current_round"]
            else ""
        )
        lines.extend(
            [
                heading,
                "",
                (
                    f"- 当前：**{application['current_stage']}**{current_round}"
                    f"｜{application['status_label']}"
                ),
                "- 流程：",
            ]
        )
        ledger_action = redact_text(str(application.get("ledger_action") or ""))
        if ledger_action:
            lines.insert(len(lines) - 1, f"- 下一步：{ledger_action}")
        for event in application["history"]:  # type: ignore[union-attr]
            time_label = "时间待确认"
            if event["time"]:
                time_label = datetime.fromisoformat(str(event["time"])).astimezone(
                    SHANGHAI
                ).strftime("%Y-%m-%d %H:%M")
            round_label = f"｜{event['round']}" if event["round"] else ""
            lines.append(
                f"  - {time_label}｜{event['stage']}{round_label}｜{event['status_label']}"
            )
        lines.append("")
    lines.extend([MANAGED_END, ""])
    _atomic_write(
        output,
        prefix.rstrip() + "\n\n" + "\n".join(lines) + suffix.lstrip(),
    )
    return len(applications)
