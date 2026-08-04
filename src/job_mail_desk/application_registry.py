from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

import yaml

from .markdown_store import FRONTMATTER, _atomic_write
from .models import ApplicationRecord
from .normalization import (
    canonical_company,
    canonical_role,
    is_invalid_role,
    normalize_company_project,
    role_key,
)
from .parser import SHANGHAI
from .progress import read_progress_entries


JOB_CODE = re.compile(r"\b([A-Za-z]\d{4,})\b", re.IGNORECASE)
YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
SUBMITTED_DATE = re.compile(
    r"(?P<year>20\d{2})[-./年](?P<month>\d{1,2})[-./月](?P<day>\d{1,2})日?"
    r"[^。；;]{0,20}(?:投递|网申)"
)
APPLICATION_MARKER = re.compile(
    r"<!--\s*jobmaildesk:application:(?P<id>(?:app-)?[0-9a-f]{20,64})\s*-->"
)
PLACEHOLDER_COMPANIES = {"", "公司待确认", "未知公司", "待确认"}


def _normalized_key(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).casefold()


def _company_key(company: str) -> str:
    normalized, _ = normalize_company_project(company)
    return _normalized_key(normalized) or "unknown-company"


def _program(role: str, project: str | None = None) -> str | None:
    combined = " ".join(item for item in (project, role) if item)
    for label in ("JDS", "TET", "TGT"):
        if re.search(rf"(?<![A-Za-z]){label}(?![A-Za-z])", combined, re.I):
            return label
    return project or None


def _business_unit(company: str, role: str, project: str | None = None) -> str | None:
    combined = f"{company} {role} {project or ''}"
    if "雷火" in combined:
        return "雷火事业群"
    if "互娱" in combined:
        return "互娱事业群"
    return None


def _submitted_at(status: str, action: str) -> datetime | None:
    match = SUBMITTED_DATE.search(f"{status} {action}")
    if not match:
        return None
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            tzinfo=SHANGHAI,
        )
    except ValueError:
        return None


def stable_application_key(
    *,
    company: str,
    role: str | None,
    recruiting_project: str | None,
    recruiting_year: int | None,
    business_unit: str | None,
    job_code: str | None,
    legacy_application_id: str | None = None,
) -> str:
    company_value = _company_key(company)
    if job_code:
        identity = f"{company_value}|job-code|{job_code.upper()}"
    elif legacy_application_id:
        identity = f"legacy-application|{legacy_application_id}"
    else:
        identity = "|".join(
            (
                company_value,
                _normalized_key(recruiting_project or "unknown-project"),
                str(recruiting_year or "unknown-year"),
                _normalized_key(business_unit or "unknown-unit"),
                role_key(canonical_role(role) or role or "unknown-role"),
            )
        )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"app-{digest}"


def application_from_progress_entry(
    entry: dict[str, str],
    *,
    now: datetime | None = None,
) -> ApplicationRecord | None:
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    company, normalized_project = normalize_company_project(
        entry.get("company") or "公司待确认",
        entry.get("project") or None,
    )
    raw_role = entry.get("role") or ""
    role = None if is_invalid_role(raw_role) else canonical_role(raw_role)
    code_match = JOB_CODE.search(raw_role)
    job_code = code_match.group(1).upper() if code_match else None
    year_match = YEAR.search(" ".join((raw_role, normalized_project or "")))
    recruiting_year = int(year_match.group(1)) if year_match else None
    project = _program(raw_role, normalized_project)
    business_unit = _business_unit(company, raw_role, normalized_project)
    legacy_id = entry.get("application_id") or ""
    identifiable = bool(
        job_code
        or legacy_id
        or (
            company not in PLACEHOLDER_COMPANIES
            and canonical_company(company) is not None
            and (role or project)
        )
    )
    if not identifiable:
        return None
    evidence = ["progress-ledger-row"]
    if job_code:
        evidence.append(f"job-code:{job_code}")
    if project:
        evidence.append(f"project:{project}")
    if legacy_id:
        evidence.append("legacy-application-id")
    if recruiting_year is None:
        evidence.append("recruiting-year-unresolved")
    key = stable_application_key(
        company=company,
        role=role,
        recruiting_project=project,
        recruiting_year=recruiting_year,
        business_unit=business_unit,
        job_code=job_code,
        legacy_application_id=legacy_id or None,
    )
    ended = any(
        label in (entry.get("status") or "")
        for label in ("已结束", "未通过", "撤回", "关闭", "已过期")
    )
    return ApplicationRecord(
        application_key=key,
        company_key=_company_key(company),
        company=company,
        recruiting_project=project,
        recruiting_year=recruiting_year,
        business_unit=business_unit,
        role=role,
        role_aliases=[raw_role] if raw_role and raw_role != role else [],
        job_code=job_code,
        submitted_at=_submitted_at(
            entry.get("status") or "",
            entry.get("action") or "",
        ),
        status="ended" if ended else "active",
        source="progress-ledger",
        confirmed_by_user=True,
        identity_locked=True,
        legacy_application_ids=[legacy_id] if legacy_id else [],
        identity_evidence=evidence,
        created_at=current,
        updated_at=current,
    )


def preview_progress_applications(path: Path | None) -> list[ApplicationRecord]:
    records: dict[str, ApplicationRecord] = {}
    for entry in read_progress_entries(path):
        record = application_from_progress_entry(entry)
        if record is None:
            continue
        existing = records.get(record.application_key)
        if not existing:
            records[record.application_key] = record
            continue
        existing.role_aliases = sorted(
            set(existing.role_aliases) | set(record.role_aliases)
        )
        existing.legacy_application_ids = sorted(
            set(existing.legacy_application_ids)
            | set(record.legacy_application_ids)
        )
        existing.identity_evidence = sorted(
            set(existing.identity_evidence) | set(record.identity_evidence)
        )
        if not existing.submitted_at and record.submitted_at:
            existing.submitted_at = record.submitted_at
        if record.status == "ended":
            existing.status = "ended"
        for field_name in (
            "recruiting_project",
            "recruiting_year",
            "business_unit",
            "job_code",
        ):
            existing_value = getattr(existing, field_name)
            record_value = getattr(record, field_name)
            if existing_value is None and record_value is not None:
                setattr(existing, field_name, record_value)
            elif (
                existing_value is not None
                and record_value is not None
                and existing_value != record_value
            ):
                existing.identity_evidence = sorted(
                    set(existing.identity_evidence)
                    | {f"conflict:{field_name}"}
                )
                existing.confirmed_by_user = False
                existing.identity_locked = False
        if not existing.role and record.role:
            existing.role = record.role
        existing.updated_at = max(
            item for item in (existing.updated_at, record.updated_at) if item
        )
    return sorted(
        records.values(),
        key=lambda item: (item.company, item.role or "", item.application_key),
    )


def render_application(record: ApplicationRecord) -> str:
    frontmatter = yaml.safe_dump(
        record.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return (
        f"{FRONTMATTER}\n{frontmatter}\n{FRONTMATTER}\n\n"
        f"# {record.company}｜{record.role or '岗位待确认'}\n\n"
        "## 身份边界\n\n"
        f"- 申请键：`{record.application_key}`\n"
        f"- 招聘项目：{record.recruiting_project or '待确认'}\n"
        f"- 招聘年份：{record.recruiting_year or '待确认'}\n"
        f"- 事业群：{record.business_unit or '待确认'}\n"
        f"- 职位编号：{record.job_code or '待确认'}\n"
        f"- 人工锁定：{'是' if record.identity_locked else '否'}\n\n"
        "## 证据\n\n"
        + (
            "\n".join(f"- {item}" for item in record.identity_evidence)
            if record.identity_evidence
            else "- 暂无"
        )
        + "\n\n## 说明\n\n"
        "- 本文件只保存申请身份，不保存邮件正文。\n"
        "- 已人工锁定的身份不得被邮件重放或解析器升级静默覆盖。\n"
    )


def parse_application(path: Path) -> ApplicationRecord:
    content = path.read_text(encoding="utf-8")
    if not content.startswith(f"{FRONTMATTER}\n"):
        raise ValueError(f"申请文件缺少 frontmatter：{path}")
    _, frontmatter, _ = content.split(FRONTMATTER, maxsplit=2)
    payload = yaml.safe_load(frontmatter) or {}
    return ApplicationRecord.from_dict(payload)


class ApplicationRegistry:
    def __init__(self, applications_dir: Path) -> None:
        self.applications_dir = applications_dir
        self.applications_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, application_key: str) -> Path:
        return self.applications_dir / f"{application_key}.md"

    def load(self, application_key: str) -> ApplicationRecord | None:
        path = self.path_for(application_key)
        return parse_application(path) if path.exists() else None

    def all(self, *, ignore_invalid: bool = False) -> list[ApplicationRecord]:
        records: list[ApplicationRecord] = []
        for path in sorted(self.applications_dir.glob("app-*.md")):
            try:
                records.append(parse_application(path))
            except (OSError, UnicodeError, KeyError, TypeError, ValueError, yaml.YAMLError):
                if not ignore_invalid:
                    raise
        return records

    def save(self, record: ApplicationRecord) -> Path:
        current = datetime.now(SHANGHAI)
        record.created_at = record.created_at or current
        record.updated_at = current
        path = self.path_for(record.application_key)
        _atomic_write(path, render_application(record))
        return path

    def import_progress(self, path: Path | None) -> list[ApplicationRecord]:
        imported: list[ApplicationRecord] = []
        for candidate in preview_progress_applications(path):
            existing = self.load(candidate.application_key)
            if existing and existing.identity_locked:
                existing.status = (
                    "ended"
                    if candidate.status == "ended"
                    else existing.status
                )
                if candidate.submitted_at and (
                    not existing.submitted_at
                    or candidate.submitted_at < existing.submitted_at
                ):
                    existing.submitted_at = candidate.submitted_at
                existing.role_aliases = sorted(
                    set(existing.role_aliases) | set(candidate.role_aliases)
                )
                existing.legacy_application_ids = sorted(
                    set(existing.legacy_application_ids)
                    | set(candidate.legacy_application_ids)
                )
                existing.identity_evidence = sorted(
                    set(existing.identity_evidence)
                    | set(candidate.identity_evidence)
                )
                if any(
                    evidence.startswith("conflict:")
                    for evidence in candidate.identity_evidence
                ):
                    existing.confirmed_by_user = False
                    existing.identity_locked = False
                self.save(existing)
                imported.append(existing)
                continue
            self.save(candidate)
            imported.append(candidate)
        return imported
