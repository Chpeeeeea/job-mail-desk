from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
from pathlib import Path
import re

from .markdown_store import _atomic_write
from .models import JobTask
from .normalization import (
    canonical_role,
    is_invalid_role,
    normalize_company_project,
    role_key,
)
from .parser import SHANGHAI
from .privacy import redact_text
from .task_service import critical_time


MANAGED_START = "<!-- jobmaildesk:progress-start -->"
MANAGED_END = "<!-- jobmaildesk:progress-end -->"
APPLICATION_MARKER = re.compile(
    r"<!--\s*jobmaildesk:application:(?P<id>(?:app-)?[0-9a-f]{20,64})\s*-->"
)
JOB_CODE = re.compile(r"\b([A-Za-z]\d{4,})\b", re.IGNORECASE)
STATUS_DATE = re.compile(r"^(?P<date>约?\d{4}-\d{2}-\d{2})\s*(?P<status>.*)$")
PROCESS_STAGE_LABELS = ("测评", "笔试", "面试", "群面", "终面")
ENDED_LABELS = ("已结束", "未通过", "撤回", "关闭", "应聘终止", "已归档")


def _application_identity(task: JobTask) -> str:
    return task.application_key or task.application_id


def _task_marker_ids(task: JobTask) -> set[str]:
    return {item for item in (task.application_key, task.application_id) if item}


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

> 每行使用：公司｜岗位｜当前进展｜下一步动作。JobMailDesk只读取下方“已投递或已进入流程”区域。
> 当公司和岗位能够唯一匹配时，组件完成任务会更新“当前进展”并在行尾写入稳定申请 ID；不会覆盖下一步动作和其他手写区域。
> 保存后点击组件“同步台账”，即可让申请卡片读取这里的修改；不要手动编辑 [[求职当前进展]] 的自动生成区。

## 当前进展

### 已投递或已进入流程

> 受控格式：公司｜岗位｜**当前进展**｜下一步动作 `<!-- jobmaildesk:application:稳定申请ID -->`
> 已有稳定 ID 的行可直接修改公司、岗位、当前进展和下一步；需要隐藏申请时请把当前进展改为“已归档”。

<!-- 示例：- [x] 示例公司｜产品经理｜**一面已确认**｜8月6日14:00参加面试；首次成功同步后，程序会在行尾加入稳定申请 ID。 -->

### 当前优先待投

<!-- 可自由记录尚未投递的岗位；这一部分不会自动进入求职进展卡片。 -->

## 状态约定

- `[x]`：已经投递或进入流程。
- 当前进展建议使用：已投递、测评、笔试、一面、二面、群面、Offer、未通过、已结束。
- 已完成节点建议保留日期，例如：`2026-08-03 人才测评已完成，等待后续`；截止时间与完成时间必须分开。
- 同一岗位进展变化时更新原行，不要重复追加相同岗位。

## 可编辑字段

| 字段 | 写法 | 组件行为 |
| --- | --- | --- |
| 公司 | 企业标准名 | 更新申请身份；事业群仍需写在岗位或项目中 |
| 岗位 | 精确岗位名/岗位编号 | 更新申请链岗位，不与同公司其他岗位合并 |
| 当前进展 | 已投递、测评、笔试、面试、群面、Offer、未通过、已结束 | 更新当前阶段；终止类状态停止提醒 |
| 下一步动作 | 简短可执行句子 | 更新卡片行动摘要 |
| 复选框 | `[x]` 已投递/已确认，`[ ]` 待处理 | 不覆盖历史节点完成状态 |

## 归档规则

- 想隐藏一条申请时，把当前进展改为 `已归档`，再点击“同步台账”。
- 组件保留本地任务历史，避免旧邮件重新制造重复申请链。
- 直接删除台账行不会删除本地任务；没有稳定 ID 的行会进入“待归属”，等待人工选择。
"""
    _atomic_write(path, content)
    return True


def _event_time(task: JobTask) -> datetime:
    return (
        (task.completed_at if task.status == "done" else None)
        or
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
    normalized, _project = normalize_company_project(value)
    cleaned = re.sub(r"[\s（）()【】\[\]]+", "", normalized).casefold()
    cleaned = re.sub(r"(?:校园招聘|校招)$", "", cleaned)
    return {
        "deeproute.ai": "元戎启行",
        "深圳元戎启行科技有限公司": "元戎启行",
    }.get(cleaned, cleaned)


def _role_key(value: str) -> str:
    without_code = JOB_CODE.sub("", value)
    normalized = canonical_role(without_code) or without_code
    return role_key(normalized)


def _job_codes(value: str) -> set[str]:
    return {match.upper() for match in JOB_CODE.findall(value)}


def _same_role(left: str, right: str) -> bool:
    left_codes = _job_codes(left)
    right_codes = _job_codes(right)
    if left_codes and right_codes:
        return bool(left_codes & right_codes)
    left_key = _role_key(left)
    right_key = _role_key(right)
    return bool(left_key and right_key and left_key == right_key)


def _best_role(chain: list[JobTask]) -> str | None:
    roles = [
        role
        for item in chain
        if (role := canonical_role(item.role)) and not is_invalid_role(role)
    ]
    if not roles:
        return None
    counts = {role: roles.count(role) for role in set(roles)}
    return max(roles, key=lambda role: (counts[role], -len(role)))


def _progress_status(task: JobTask) -> str:
    stage = (task.round or task.stage or "流程").strip()
    if "已完成" in stage and any(label in stage for label in ("等待后续", "等待结果")):
        return stage.replace("等待后续", "等待结果")
    if stage.startswith("等待"):
        return stage
    if task.event_type == "application" and task.status == "confirmed":
        return f"{task.received_at:%Y-%m-%d} 网申已提交，等待简历筛选"
    if task.status == "done":
        completed = ""
        if task.completed_at:
            prefix = "约" if task.completed_at_inferred else ""
            completed = f"{prefix}{task.completed_at:%Y-%m-%d} "
        if any(label in stage for label in ("测评", "笔试", "面试", "群面")):
            return f"{completed}{stage}已完成，等待后续"
        if "投递" in stage or "网申" in stage:
            return f"{completed}已投递，等待筛选"
        return f"{completed}{stage}已完成"
    if task.status == "planned":
        return f"{stage}已安排"
    if task.status == "confirmed":
        return f"{stage}已确认"
    if task.status == "cancelled":
        return f"{stage}已取消"
    if task.status == "expired":
        return f"{stage}已过期"
    return _status_label(task.status)


def _status_date(task: JobTask) -> str | None:
    value = task.completed_at if task.status == "done" and task.completed_at else critical_time(task)
    if not value:
        return None
    prefix = "约" if task.status == "done" and task.completed_at_inferred else ""
    return f"{prefix}{value.astimezone(SHANGHAI):%Y-%m-%d}"


def _split_status_date(value: str) -> tuple[str | None, str]:
    cleaned = value.strip()
    match = STATUS_DATE.match(cleaned)
    if not match:
        return None, cleaned
    return match.group("date"), match.group("status").strip()


def _ended_reason(value: str) -> str:
    text = value.strip()
    parenthetical = re.search(r"未通过[（(]([^）)]*未通过)[）)]", text)
    if parenthetical:
        text = parenthetical.group(1)
    text = re.sub(r"^已结束\s*[:：·-]?\s*", "", text)
    text = re.sub(r"应聘终止", "未通过", text)
    text = re.sub(r"已完成(?:，?等待(?:后续|结果))?$", "", text)
    text = re.sub(r"，?等待(?:后续|结果)$", "", text)
    text = re.sub(r"[（(]已结束[）)]$", "", text)
    text = text.strip(" ：:·，,")
    return text or "流程终止"


def _latest_completed_stage(application: dict[str, object]) -> str | None:
    for event in application.get("history", []):  # type: ignore[union-attr]
        if event.get("status") != "done":
            continue
        stage = str(event.get("round") or event.get("stage") or "").strip()
        if stage and "等待" not in stage:
            return stage
    return None


def _canonical_status(
    value: str,
    *,
    application: dict[str, object] | None = None,
    task: JobTask | None = None,
) -> dict[str, object]:
    date_label, status = _split_status_date(value)
    if task and not date_label:
        date_label = _status_date(task)
    prefix = f"{date_label} " if date_label else ""

    if any(label in status for label in ENDED_LABELS):
        reason = _ended_reason(status)
        result = "failed" if "未通过" in reason else (
            "withdrawn" if "撤回" in reason else "closed"
        )
        return {
            "display": f"{prefix}已结束 · {reason}",
            "application_state": "ended",
            "stage_state": "completed",
            "result": result,
            "status_at": date_label,
        }

    if "已过期" in status or (task and task.status == "expired"):
        stage = status.replace("已过期", "").strip(" ：:·，,")
        stage = stage or ((task.round or task.stage) if task else "当前事项")
        return {
            "display": f"{prefix}{stage}已过期 · 待确认",
            "application_state": "expired",
            "stage_state": "expired",
            "result": "pending",
            "status_at": date_label,
        }

    if "待确认" in status:
        return {
            "display": f"{prefix}{status}",
            "application_state": "pending",
            "stage_state": "waiting",
            "result": "pending",
            "status_at": date_label,
        }

    completed = "已完成" in status or (task and task.status == "done")
    if completed:
        stage = status
        if "等待" in stage:
            stage = stage.split("等待", 1)[0].rstrip("，, ")
        stage = re.sub(r"已完成$", "", stage).strip()
        if not stage or stage == "后续":
            stage = _latest_completed_stage(application or {}) or (
                (task.round or task.stage) if task else "当前环节"
            )
        process_completed = any(label in stage for label in PROCESS_STAGE_LABELS)
        suffix = "已完成，等待结果" if process_completed else "，等待后续"
        return {
            "display": f"{prefix}{stage}{suffix}",
            "application_state": "active",
            "stage_state": "completed" if process_completed else "waiting",
            "result": "pending",
            "status_at": date_label,
        }

    stage_state = "scheduled" if "已安排" in status else (
        "waiting" if "等待" in status or "筛选" in status else "active"
    )
    return {
        "display": value.strip(),
        "application_state": "active",
        "stage_state": stage_state,
        "result": "pending",
        "status_at": date_label,
    }


def sync_task_to_ledger(task: JobTask, path: Path | None) -> int:
    """Update one uniquely matched ledger row without touching user-owned fields."""
    if not path or not path.exists() or task.status == "irrelevant":
        return 0
    content = path.read_text(encoding="utf-8")
    marker = "### 已投递或已进入流程"
    if marker not in content:
        return 0
    prefix, section_and_suffix = content.split(marker, 1)
    if "\n### " in section_and_suffix:
        section, suffix = section_and_suffix.split("\n### ", 1)
        suffix = "\n### " + suffix
    else:
        section, suffix = section_and_suffix, ""

    candidates: list[tuple[int, str, list[str], str]] = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^- \[[ xX]\] ", line):
            continue
        marker_match = APPLICATION_MARKER.search(line)
        clean_line = APPLICATION_MARKER.sub("", line).rstrip()
        body = clean_line.split("] ", 1)[1]
        fields = body.split("｜")
        if len(fields) < 3:
            continue
        company = re.sub(r"[*_`]", "", fields[0]).strip()
        role = re.sub(r"[*_`]", "", fields[1]).strip()
        marker_id = marker_match.group("id") if marker_match else ""
        if marker_id in _task_marker_ids(task):
            candidates = [(
                index,
                line,
                fields,
                clean_line.split("] ", 1)[0] + "] ",
            )]
            break
        if (
            not marker_id
            and _company_key(company) == _company_key(task.company)
            and task.role
            and _same_role(role, task.role)
        ):
            candidates.append(
                (
                    index,
                    line,
                    fields,
                    clean_line.split("] ", 1)[0] + "] ",
                )
            )

    if not candidates and task.event_type == "application" and task.role:
        checked = "x" if task.status in {"confirmed", "done"} else " "
        lines.extend(
            [
                "",
                (
                    f"- [{checked}] {task.company}｜{task.role}｜"
                    f"**{_progress_status(task)}**｜{task.action_summary} "
                    f"<!-- jobmaildesk:application:{_application_identity(task)} -->"
                ),
            ]
        )
        updated = prefix + marker + "\n".join(lines) + suffix
        _atomic_write(path, updated)
        return 1
    if len(candidates) != 1:
        return 0
    index, _line, fields, _checkbox_prefix = candidates[0]
    existing_status = re.sub(r"[*_`]", "", fields[2]).strip()
    if _canonical_status(existing_status)["application_state"] == "ended":
        # The user-maintained ledger is the control plane. A normal scan may
        # append history, but it must not reopen an explicitly ended chain.
        return 0
    checked = task.status == "done" or (
        task.event_type == "application" and task.status == "confirmed"
    )
    checkbox_prefix = "- [x] " if checked else "- [ ] "
    fields[2] = f"**{_progress_status(task)}**"
    lines[index] = (
        f"{checkbox_prefix}{'｜'.join(fields)} "
        f"<!-- jobmaildesk:application:{_application_identity(task)} -->"
    )
    updated = prefix + marker + "\n".join(lines) + suffix
    if updated == content:
        return 0
    _atomic_write(path, updated)
    return 1


def update_application_status_in_ledger(
    task: JobTask,
    path: Path | None,
    application_state: str,
    result: str = "",
) -> int:
    """Update one application's user-owned status without rewriting task history."""
    if application_state not in {"active", "pending", "ended"}:
        raise ValueError(f"不支持的申请链状态：{application_state}")
    if not path or not path.exists():
        raise ValueError("未配置可编辑的岗位投递决策台账。")
    detail = result.strip(" ：:·，,")
    if application_state == "ended" and not detail:
        raise ValueError("将申请链设为已结束时，请填写结果或原因。")
    today = datetime.now(SHANGHAI).date().isoformat()
    status = {
        "active": detail or f"{task.round or task.stage}进行中",
        "pending": detail or f"{task.round or task.stage}待确认",
        "ended": f"{today} 已结束 · {detail}",
    }[application_state]

    content = path.read_text(encoding="utf-8")
    marker = "### 已投递或已进入流程"
    if marker not in content:
        raise ValueError("岗位投递决策台账缺少已投递区。")
    prefix, section_and_suffix = content.split(marker, 1)
    if "\n### " in section_and_suffix:
        section, suffix = section_and_suffix.split("\n### ", 1)
        suffix = "\n### " + suffix
    else:
        section, suffix = section_and_suffix, ""

    candidates: list[tuple[int, list[str], str]] = []
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^- \[[ xX]\] ", line):
            continue
        marker_match = APPLICATION_MARKER.search(line)
        clean_line = APPLICATION_MARKER.sub("", line).rstrip()
        fields = clean_line.split("] ", 1)[1].split("｜")
        if len(fields) < 3:
            continue
        marker_id = marker_match.group("id") if marker_match else ""
        company = re.sub(r"[*_`]", "", fields[0]).strip()
        role = re.sub(r"[*_`]", "", fields[1]).strip()
        if marker_id in _task_marker_ids(task):
            candidates = [(index, fields, clean_line.split("] ", 1)[0] + "] ")]
            break
        if (
            not marker_id
            and _company_key(company) == _company_key(task.company)
            and task.role
            and _same_role(role, task.role)
        ):
            candidates.append((index, fields, clean_line.split("] ", 1)[0] + "] "))
    if len(candidates) != 1:
        raise ValueError("无法唯一定位对应的申请链，请先确认公司和岗位归属。")
    index, fields, checkbox_prefix = candidates[0]
    fields[2] = f"**{status}**"
    lines[index] = (
        f"{checkbox_prefix}{'｜'.join(fields)} "
        f"<!-- jobmaildesk:application:{_application_identity(task)} -->"
    )
    updated = prefix + marker + "\n".join(lines) + suffix
    if updated == content:
        return 0
    _atomic_write(path, updated)
    return 1


def sync_current_applications_to_ledger(
    tasks: list[JobTask],
    path: Path | None,
) -> int:
    """Sync each application once, using its current node after batch merging."""
    grouped: dict[str, list[JobTask]] = defaultdict(list)
    for task in tasks:
        if task.status != "irrelevant":
            grouped[_application_identity(task)].append(task)
    updates = 0
    for chain in grouped.values():
        chain.sort(key=_event_time)
        active = [
            item
            for item in chain
            if item.status not in {"done", "cancelled", "expired", "irrelevant"}
        ]
        current = active[-1] if active else chain[-1]
        updates += sync_task_to_ledger(current, path)
    return updates


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
        marker_match = APPLICATION_MARKER.search(line)
        clean_line = APPLICATION_MARKER.sub("", line).rstrip()
        fields = [
            re.sub(r"[*_`]", "", item).strip()
            for item in clean_line.split("] ", 1)[1].split("｜")
        ]
        if len(fields) < 3:
            continue
        company, project = normalize_company_project(fields[0])
        entries.append(
            {
                "company": company,
                "role": canonical_role(fields[1]) or fields[1],
                "project": project or "",
                "status": fields[2],
                "action": "｜".join(fields[3:]).strip(),
                "application_id": marker_match.group("id") if marker_match else "",
            }
        )
    return entries


def read_progress_entries(path: Path | None) -> list[dict[str, str]]:
    """Return normalized user-ledger rows without modifying the source file."""
    return [dict(entry) for entry in _ledger_entries(path)]


def progress_payload(
    tasks: list[JobTask],
    source_path: Path | None = None,
) -> list[dict[str, object]]:
    """Build application-chain progress without actionable-list filtering."""
    grouped: dict[str, list[JobTask]] = defaultdict(list)
    for task in tasks:
        if task.status != "irrelevant":
            grouped[_application_identity(task)].append(task)

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
        role = _best_role(chain)
        project = next(
            (item.recruiting_project for item in reversed(chain) if item.recruiting_project),
            None,
        )
        company, project = normalize_company_project(company, project)
        history = [
            {
                "task_id": item.id,
                "stage": item.stage,
                "round": item.round or "",
                "status": item.status,
                "status_label": _status_label(item.status),
                "time": (
                    item.completed_at
                    if item.status == "done" and item.completed_at
                    else critical_time(item)
                ).isoformat()
                if (
                    (item.status == "done" and item.completed_at)
                    or critical_time(item)
                )
                else None,
                "action": item.action_summary,
                "time_inferred": bool(
                    item.status == "done"
                    and item.completed_at
                    and item.completed_at_inferred
                ),
            }
            for item in reversed(chain)
        ]
        application: dict[str, object] = {
                "application_id": app_id,
                "application_key": current.application_key,
                "legacy_application_id": current.application_id,
                "company": company,
                "role": role or "岗位待确认",
                "project": project or "",
                "current_stage": current.stage,
                "current_round": current.round or "",
                "current_status": current.status,
                "status_label": _status_label(current.status),
                "received_at": current.received_at.isoformat(),
                "start_at": current.start_at.isoformat() if current.start_at else None,
                "end_at": current.end_at.isoformat() if current.end_at else None,
                "deadline_at": (
                    current.deadline_at.isoformat() if current.deadline_at else None
                ),
                "completed_at": (
                    current.completed_at.isoformat() if current.completed_at else None
                ),
                "completed_at_inferred": current.completed_at_inferred,
                "current_action": current.action_summary,
                "active": bool(active),
                "next_time": (
                    critical_time(current).isoformat()
                    if critical_time(current) and critical_time(current) >= datetime.now(SHANGHAI)
                    else None
                ),
                "updated_at": _event_time(current).isoformat(),
                "history": history,
            }
        status_meta = _canonical_status(
            _progress_status(current), application=application, task=current
        )
        application["current_stage"] = status_meta["display"]
        application["status_label"] = status_meta["display"]
        application["application_state"] = status_meta["application_state"]
        application["stage_state"] = status_meta["stage_state"]
        application["result"] = status_meta["result"]
        application["status_at"] = status_meta["status_at"]
        application["active"] = status_meta["application_state"] == "active"
        applications.append(application)

    task_applications = list(applications)
    ledger_keys: set[tuple[str, str]] = set()
    task_states: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        task_states[_company_key(task.company)].add(task.status)
    for entry in _ledger_entries(source_path):
        company_key = _company_key(entry["company"])

        def same_program(application: dict[str, object]) -> bool:
            application_text = " ".join(
                (str(application.get("role") or ""), str(application.get("project") or ""))
            )
            ledger_text = " ".join((entry["role"], entry["project"]))
            application_program = re.search(r"(?<![A-Za-z])(JDS|TET)(?![A-Za-z])", application_text, re.I)
            ledger_program = re.search(r"(?<![A-Za-z])(JDS|TET)(?![A-Za-z])", ledger_text, re.I)
            return bool(
                application_program
                and ledger_program
                and application_program.group(1).casefold()
                == ledger_program.group(1).casefold()
            )

        task_matches = [
            application
            for application in task_applications
            if (
                entry["application_id"]
                in {
                    application["application_id"],
                    application.get("application_key"),
                    application.get("legacy_application_id"),
                }
                or (
                    not entry["application_id"]
                    and _company_key(str(application["company"])) == company_key
                    and (
                        _same_role(str(application["role"]), entry["role"])
                        or same_program(application)
                    )
                    and (
                        not entry["project"]
                        or entry["project"] in str(application["project"])
                    )
                )
            )
        ]
        if task_matches:
            for application in task_matches:
                # The user-maintained ledger is the editable control plane for
                # application identity and current progress. Stable markers
                # make these overrides deterministic without rewriting task
                # history.
                application["company"] = entry["company"] or application["company"]
                application["role"] = entry["role"] or application["role"]
                if entry["project"] and not application["project"]:
                    application["project"] = entry["project"]
                application["ledger_status"] = entry["status"]
                application["ledger_action"] = entry["action"]
                # 人工台账是申请结果的权威来源。邮件链可能停留在“测评已完成”
                # 等历史节点；当台账明确写出未通过、应聘终止或已结束时，
                # 当前卡片必须展示终止结果，但保留原有 history 供复盘。
                if entry["status"]:
                    status_meta = _canonical_status(
                        entry["status"], application=application
                    )
                    application["current_stage"] = status_meta["display"]
                    application["status_label"] = status_meta["display"]
                    application["application_state"] = status_meta[
                        "application_state"
                    ]
                    application["stage_state"] = status_meta["stage_state"]
                    application["result"] = status_meta["result"]
                    application["status_at"] = status_meta["status_at"]
                    application["current_action"] = entry["action"]
                    application["active"] = (
                        status_meta["application_state"] == "active"
                    )
                    if not application["active"]:
                        application["next_time"] = None
                        application["current_status"] = (
                            "expired"
                            if status_meta["application_state"] == "expired"
                            else "done"
                        )
                if application["role"] == "岗位待确认" and same_program(application):
                    application["role"] = entry["role"]
            continue
        if task_states.get(company_key) == {"irrelevant"}:
            continue
        ledger_key = (company_key, _role_key(entry["role"]))
        if ledger_key in ledger_keys:
            continue
        status_meta = _canonical_status(entry["status"])
        ended = status_meta["application_state"] == "ended"
        expired = status_meta["application_state"] == "expired"
        identifier = hashlib.sha256(
            f"ledger|{entry['company']}|{entry['role']}".encode("utf-8")
        ).hexdigest()[:20]
        applications.append(
            {
                "application_id": identifier,
                "company": entry["company"],
                "role": entry["role"],
                "project": entry["project"],
                "current_stage": status_meta["display"],
                "current_round": "",
                "current_status": "done" if ended else ("expired" if expired else "tracked"),
                "status_label": status_meta["display"],
                "application_state": status_meta["application_state"],
                "stage_state": status_meta["stage_state"],
                "result": status_meta["result"],
                "status_at": status_meta["status_at"],
                "received_at": None,
                "start_at": None,
                "end_at": None,
                "deadline_at": None,
                "completed_at": None,
                "completed_at_inferred": False,
                "current_action": entry["action"],
                "active": not ended and not expired,
                "next_time": None,
                "updated_at": "",
                "ledger_status": entry["status"],
                "ledger_action": entry["action"],
                "history": [
                    {
                        "task_id": None,
                        "stage": entry["status"],
                        "round": "",
                        "status": "done" if ended else ("expired" if expired else "tracked"),
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

    def cell(value: object) -> str:
        text = redact_text(str(value or "")).replace("|", "\\|").strip()
        return text or "—"

    def display_time(value: object, *, inferred: bool = False) -> str:
        if not value:
            return "—"
        rendered = datetime.fromisoformat(str(value)).astimezone(SHANGHAI).strftime(
            "%Y-%m-%d %H:%M"
        )
        return f"约 {rendered}（历史推定）" if inferred else rendered

    for application in applications:
        company = redact_text(str(application["company"]))
        role = redact_text(str(application["role"]))
        project = redact_text(str(application["project"]))
        summary = f"{company}｜{role} · {application['current_stage']}"
        current_round = (
            str(application["current_round"])
            if application["current_round"]
            else "—"
        )
        next_action = redact_text(
            str(
                application.get("ledger_action")
                or application.get("current_action")
                or ""
            )
        )
        if application.get("start_at") and application.get("end_at"):
            activity_window = (
                f"{display_time(application['start_at'])} – "
                f"{display_time(application['end_at'])}"
            )
        else:
            activity_window = display_time(application.get("start_at"))
        lines.extend(
            [
                f"> [!abstract]- {summary}",
                f"> <!-- jobmaildesk:application:{application['application_id']} -->",
                ">",
                "> | 字段 | 内容 |",
                "> | --- | --- |",
                f"> | 企业 | {cell(company)} |",
                f"> | 岗位 | {cell(role)} |",
                f"> | 招聘项目 | {cell(project)} |",
                f"> | 当前阶段 | {cell(application['current_stage'])} |",
                f"> | 当前状态 | {cell(application['status_label'])} |",
                f"> | 轮次 | {cell(current_round)} |",
                f"> | 投递/收到 | {display_time(application.get('received_at'))} |",
                f"> | 活动窗口 | {activity_window} |",
                f"> | 截止时间 | {display_time(application.get('deadline_at'))} |",
                (
                    "> | 完成时间 | "
                    f"{display_time(application.get('completed_at'), inferred=bool(application.get('completed_at_inferred')))} |"
                ),
                f"> | 下一步 | {cell(next_action)} |",
                ">",
                "> **流程记录**",
            ]
        )
        for event in application["history"]:  # type: ignore[union-attr]
            time_label = "时间待确认"
            if event["time"]:
                time_label = datetime.fromisoformat(str(event["time"])).astimezone(
                    SHANGHAI
                ).strftime("%Y-%m-%d %H:%M")
                if event.get("time_inferred"):
                    time_label = f"约 {time_label}（历史推定）"
            round_label = f"｜{event['round']}" if event["round"] else ""
            checkbox = "x" if event["status"] == "done" else " "
            task_marker = (
                f" <!-- jobmaildesk:{event['task_id']} -->"
                if event["task_id"]
                else ""
            )
            lines.append(
                f"> - [{checkbox}] {time_label}｜{event['stage']}"
                f"{round_label}｜{event['status_label']}{task_marker}"
            )
        lines.extend([">", ""])
    lines.extend([MANAGED_END, ""])
    _atomic_write(
        output,
        prefix.rstrip() + "\n\n" + "\n".join(lines) + suffix.lstrip(),
    )
    return len(applications)
