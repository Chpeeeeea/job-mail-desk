from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import re

import yaml

from .identity_pipeline import IdentityDecision
from .markdown_store import FRONTMATTER, _atomic_write
from .privacy import redact_text


def _private_safe(value: str) -> str:
    return re.sub(r"https?://\S+", "[链接已隐藏]", redact_text(value)).strip()


@dataclass(frozen=True)
class UnresolvedRecord:
    id: str
    status: str
    resolution_status: str
    reason: str
    company: str | None
    role: str | None
    recruiting_project: str | None
    event_type: str
    stage: str
    round: str | None
    received_at: datetime
    start_at: datetime | None
    end_at: datetime | None
    deadline_at: datetime | None
    action_summary: str
    title: str
    requirements: tuple[str, ...]
    confidence: float
    change_type: str
    candidate_application_keys: tuple[str, ...]
    resolved_application_key: str | None
    resolved_task_id: str | None
    rule_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "status": self.status,
            "resolution_status": self.resolution_status,
            "reason": self.reason,
            "company": self.company,
            "role": self.role,
            "recruiting_project": self.recruiting_project,
            "event_type": self.event_type,
            "stage": self.stage,
            "round": self.round,
            "received_at": self.received_at.isoformat(),
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "deadline_at": self.deadline_at.isoformat()
            if self.deadline_at
            else None,
            "action_summary": self.action_summary,
            "title": self.title,
            "requirements": list(self.requirements),
            "confidence": self.confidence,
            "change_type": self.change_type,
            "candidate_application_keys": list(
                self.candidate_application_keys
            ),
            "resolved_application_key": self.resolved_application_key,
            "resolved_task_id": self.resolved_task_id,
            "rule_version": self.rule_version,
        }


def unresolved_from_decision(
    source_hash: str,
    decision: IdentityDecision,
) -> UnresolvedRecord:
    event = decision.event
    return UnresolvedRecord(
        id=source_hash,
        status="pending",
        resolution_status=decision.resolution.status,
        reason=decision.resolution.reason,
        company=_private_safe(event.company or "") or None,
        role=_private_safe(event.role or "") or None,
        recruiting_project=_private_safe(event.recruiting_project or "") or None,
        event_type=_private_safe(event.event_type),
        stage=_private_safe(event.stage),
        round=_private_safe(event.round or "") or None,
        received_at=event.source_received_at,
        start_at=event.start_at,
        end_at=event.end_at,
        deadline_at=event.deadline_at,
        action_summary=_private_safe(event.action_summary)[:240],
        title=_private_safe(event.title)[:240],
        requirements=tuple(
            _private_safe(item)[:240]
            for item in event.requirements
            if _private_safe(item)
        ),
        confidence=event.confidence,
        change_type=event.change_type,
        candidate_application_keys=tuple(
            item.application_key for item in decision.resolution.candidates
        ),
        resolved_application_key=None,
        resolved_task_id=None,
        rule_version=decision.resolution.rule_version,
    )


def render_unresolved(record: UnresolvedRecord) -> str:
    frontmatter = yaml.safe_dump(
        record.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return (
        f"{FRONTMATTER}\n{frontmatter}\n{FRONTMATTER}\n\n"
        f"# {record.company or '公司待确认'}｜{record.stage}\n\n"
        "## 邮件摘要\n\n"
        f"- 标题：{record.title or '未提供'}\n"
        f"- 类型：{record.event_type}\n"
        f"- 动作：{record.action_summary or '待人工确认'}\n\n"
        "## 待归属原因\n\n"
        f"- {record.reason}\n\n"
        "## 候选申请\n\n"
        + (
            "\n".join(
                f"- `{key}`" for key in record.candidate_application_keys
            )
            if record.candidate_application_keys
            else "- 暂无唯一候选"
        )
        + "\n\n## 隐私边界\n\n"
        "- 不保存邮件正文、发件人地址、私人通知链接或认证参数。\n"
    )


class UnresolvedStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, source_hash: str) -> Path:
        return self.directory / f"{source_hash}.md"

    def save(self, record: UnresolvedRecord) -> Path:
        path = self.path_for(record.id)
        _atomic_write(path, render_unresolved(record))
        return path

    def load(self, source_hash: str) -> UnresolvedRecord | None:
        return next((item for item in self.all() if item.id == source_hash), None)

    def resolve(
        self,
        source_hash: str,
        *,
        application_key: str,
        task_id: str,
    ) -> UnresolvedRecord:
        record = self.load(source_hash)
        if not record:
            raise KeyError(source_hash)
        updated = replace(
            record,
            status="resolved",
            resolved_application_key=application_key,
            resolved_task_id=task_id,
        )
        self.save(updated)
        return updated

    def ignore(self, source_hash: str) -> UnresolvedRecord:
        record = self.load(source_hash)
        if not record:
            raise KeyError(source_hash)
        updated = replace(record, status="ignored")
        self.save(updated)
        return updated

    def all(self) -> list[UnresolvedRecord]:
        records: list[UnresolvedRecord] = []
        for path in sorted(self.directory.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            if not content.startswith(f"{FRONTMATTER}\n"):
                raise ValueError(f"待归属文件缺少 frontmatter：{path}")
            _, raw, _ = content.split(FRONTMATTER, maxsplit=2)
            payload = yaml.safe_load(raw) or {}
            records.append(
                UnresolvedRecord(
                    id=str(payload["id"]),
                    status=str(payload.get("status") or "pending"),
                    resolution_status=str(
                        payload.get("resolution_status") or "unresolved"
                    ),
                    reason=str(payload.get("reason") or "unknown"),
                    company=str(payload["company"])
                    if payload.get("company")
                    else None,
                    role=str(payload["role"])
                    if payload.get("role")
                    else None,
                    recruiting_project=str(payload["recruiting_project"])
                    if payload.get("recruiting_project")
                    else None,
                    event_type=str(payload.get("event_type") or "notice"),
                    stage=str(payload.get("stage") or "招聘通知"),
                    round=str(payload["round"])
                    if payload.get("round")
                    else None,
                    received_at=datetime.fromisoformat(
                        str(payload["received_at"])
                    ),
                    start_at=datetime.fromisoformat(str(payload["start_at"]))
                    if payload.get("start_at")
                    else None,
                    end_at=datetime.fromisoformat(str(payload["end_at"]))
                    if payload.get("end_at")
                    else None,
                    deadline_at=datetime.fromisoformat(
                        str(payload["deadline_at"])
                    )
                    if payload.get("deadline_at")
                    else None,
                    action_summary=str(payload.get("action_summary") or ""),
                    title=str(payload.get("title") or ""),
                    requirements=tuple(
                        str(item) for item in payload.get("requirements", [])
                    ),
                    confidence=float(payload.get("confidence") or 0),
                    change_type=str(payload.get("change_type") or "new"),
                    candidate_application_keys=tuple(
                        str(item)
                        for item in payload.get(
                            "candidate_application_keys", []
                        )
                    ),
                    resolved_application_key=(
                        str(payload["resolved_application_key"])
                        if payload.get("resolved_application_key")
                        else None
                    ),
                    resolved_task_id=(
                        str(payload["resolved_task_id"])
                        if payload.get("resolved_task_id")
                        else None
                    ),
                    rule_version=str(
                        payload.get("rule_version")
                        or "identity-registry-v1"
                    ),
                )
            )
        return records
