from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import timedelta

from .application_registry import stable_application_key
from .identity_dictionaries import IdentityDictionaries
from .identity_resolver import (
    IdentityCandidate,
    IdentityResolver,
    ResolutionResult,
)
from .models import ApplicationRecord, ParsedEvent
from .normalization import canonical_role, normalize_company_project
from .normalization import is_invalid_role


JOB_CODE = re.compile(r"\b([A-Za-z]\d{4,})\b", re.IGNORECASE)
ROLE_WITH_JOB_CODE = re.compile(
    r"(?:20\d{2}|2\d届)?[^()\r\n]{0,80}?[-—－–:：]\s*"
    r"(?P<role>[^()\r\n,，;；]{2,80}?)\s*[\(（]\s*"
    r"(?P<code>[A-Za-z]\d{4,})\s*[\)）]",
    re.IGNORECASE,
)
RECRUITING_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
BATCH_CONTEXT_WINDOW = timedelta(hours=2)
PROJECT_CODE = re.compile(r"(?<![A-Za-z])(JDS|TET|TGT)(?![A-Za-z])", re.I)
GENERIC_PROJECT_SUFFIX = re.compile(
    r"(?:[·•|｜/\-]\s*)?(?:20\d{2}\s*)?"
    r"(?:校园招聘|校招|秋招|春招|提前批|正式批)$"
)
APPLICATION_STAGE = re.compile(r"网申|投递|申请|简历")


def _extract_job_identity(event: ParsedEvent) -> tuple[str | None, str | None]:
    """Recover a strong job identity from standardized mail summaries.

    Many ATS receipts do not expose a role in the parser's dedicated role
    field.  They do, however, include a stable job code in the action summary,
    for example ``27届校招-AI产品经理(J14379)``.  The code is stronger than a
    generic "application received" template and lets Core create a distinct
    application chain without an LLM.
    """

    sources = (
        event.action_summary,
        event.title,
        event.role or "",
        event.recruiting_project or "",
    )
    for source in sources:
        if not source:
            continue
        code_match = JOB_CODE.search(source)
        if not code_match:
            continue
        code = code_match.group(1).upper()
        role_match = ROLE_WITH_JOB_CODE.search(source)
        if role_match and role_match.group("code").upper() == code:
            role = canonical_role(role_match.group("role"))
            return code, role
        return code, None
    return None, None


@dataclass(frozen=True)
class IdentityDecision:
    event: ParsedEvent
    candidate: IdentityCandidate
    resolution: ResolutionResult
    action: str
    application_key: str | None

    def to_preview(self) -> dict[str, object]:
        return {
            "company": self.event.company,
            "role": self.event.role,
            "project": self.event.recruiting_project,
            "stage": self.event.stage,
            "round": self.event.round,
            "received_at": self.event.source_received_at.isoformat(),
            "start_at": self.event.start_at.isoformat()
            if self.event.start_at
            else None,
            "end_at": self.event.end_at.isoformat()
            if self.event.end_at
            else None,
            "deadline_at": self.event.deadline_at.isoformat()
            if self.event.deadline_at
            else None,
            "identity_action": self.action,
            "application_key": self.application_key,
            "resolution_status": self.resolution.status,
            "resolution_reason": self.resolution.reason,
            "candidate_count": len(self.resolution.candidates),
            "candidate_application_keys": [
                item.application_key for item in self.resolution.candidates
            ],
        }


def identity_candidate_from_event(
    event: ParsedEvent,
    dictionaries: IdentityDictionaries | None = None,
) -> IdentityCandidate:
    company, project = normalize_company_project(
        event.company or "公司待确认",
        event.recruiting_project,
    )
    role = canonical_role(event.role)
    extracted_job_code, extracted_role = _extract_job_identity(event)
    if not role and extracted_role:
        role = extracted_role
    project_source = " ".join(item for item in (project, role) if item)
    project_code = PROJECT_CODE.search(project_source)
    if project_code:
        project = project_code.group(1).upper()
    elif project:
        project = GENERIC_PROJECT_SUFFIX.sub("", project).strip(" ·•|｜/-") or None
    combined = " ".join(
        item
        for item in (event.title, role, project, event.action_summary)
        if item
    )
    code_match = JOB_CODE.search(combined)
    year_source = " ".join(item for item in (role, project) if item)
    year_match = RECRUITING_YEAR.search(year_source)
    business_unit = None
    unit_source = f"{company} {role or ''} {project or ''}"
    if "雷火" in unit_source:
        business_unit = "雷火事业群"
        project = "雷火事业群"
    elif "互娱" in unit_source:
        business_unit = "互娱事业群"
        project = "互娱事业群"
    template = None
    if dictionaries:
        template = dictionaries.mail_template_for(
            company=company,
            title=event.title,
            content=" ".join((event.action_summary, *event.requirements)),
        )
    return IdentityCandidate(
        company=company,
        role=role,
        recruiting_project=project,
        recruiting_year=int(year_match.group(1)) if year_match else None,
        business_unit=business_unit,
        job_code=(
            extracted_job_code
            or (code_match.group(1).upper() if code_match else None)
        ),
        template_id=str(template["id"]) if template else None,
    )


def _new_application_key(
    event: ParsedEvent,
    candidate: IdentityCandidate,
    resolution: ResolutionResult,
    dictionaries: IdentityDictionaries,
) -> str | None:
    strong_code_conflict = bool(
        candidate.job_code
        and resolution.candidates
        and all("job-code" in item.conflicts for item in resolution.candidates)
    )
    if resolution.candidates and not strong_code_conflict:
        return None
    if not candidate.company or candidate.company == "公司待确认":
        return None
    if not APPLICATION_STAGE.search(event.stage):
        return None
    if candidate.template_id:
        template = next(
            (
                item
                for item in dictionaries.mail_templates
                if item["id"] == candidate.template_id
            ),
            None,
        )
        # Reviewed generic receipt templates normally attach to an existing
        # chain.  When the mail carries a stable ATS job code, it is also a
        # valid first signal for a new chain (e.g. J14379/J14390).  Keep the
        # conservative behavior for code-less generic receipts so a plain
        # "we received your application" message cannot create a duplicate.
        if (
            template
            and template.get("creates_application") is False
            and not candidate.job_code
        ):
            return None
    if candidate.role and (
        is_invalid_role(candidate.role) or len(candidate.role) > 120
    ):
        return None
    if not (
        candidate.role
        or candidate.recruiting_project
        or candidate.job_code
    ):
        return None
    return stable_application_key(
        company=candidate.company,
        role=candidate.role,
        recruiting_project=candidate.recruiting_project,
        recruiting_year=candidate.recruiting_year,
        business_unit=candidate.business_unit,
        job_code=candidate.job_code,
    )


def _company_identity(
    dictionaries: IdentityDictionaries,
    company: str | None,
) -> str:
    return dictionaries.company_id(company) or (company or "").casefold().strip()


def resolve_event_batch(
    events: list[ParsedEvent],
    applications: list[ApplicationRecord],
    dictionaries: IdentityDictionaries,
) -> list[IdentityDecision]:
    resolver = IdentityResolver(dictionaries)
    decisions: list[IdentityDecision] = []
    provisional = list(applications)
    for event in events:
        candidate = identity_candidate_from_event(event, dictionaries)
        resolution = resolver.resolve(candidate, provisional)
        if resolution.status == "matched":
            action = "matched"
            application_key = resolution.application_key
        elif resolution.status == "conflict":
            # A different explicit ATS job code is evidence for a separate
            # application, not an identity ambiguity.  Keep true conflicts
            # (same code, multiple candidates or project mismatch) pending.
            application_key = (
                _new_application_key(event, candidate, resolution, dictionaries)
                if event.event_type == "application"
                else None
            )
            action = "new_application" if application_key else "conflict"
        else:
            application_key = (
                _new_application_key(event, candidate, resolution, dictionaries)
                if event.event_type == "application"
                else None
            )
            action = "new_application" if application_key else "unresolved"
        decisions.append(
            IdentityDecision(
                event=event,
                candidate=candidate,
                resolution=resolution,
                action=action,
                application_key=application_key,
            )
        )
        if action == "new_application" and application_key:
            provisional.append(
                ApplicationRecord(
                    application_key=application_key,
                    company_key=_company_identity(dictionaries, candidate.company),
                    company=candidate.company or "公司待确认",
                    recruiting_project=candidate.recruiting_project,
                    recruiting_year=candidate.recruiting_year,
                    business_unit=candidate.business_unit,
                    role=candidate.role,
                    role_aliases=[],
                    job_code=candidate.job_code,
                    submitted_at=event.source_received_at,
                    status="active",
                    source="mail-batch-preview",
                    confirmed_by_user=False,
                    identity_locked=False,
                    identity_evidence=["explicit-application-mail"],
                )
            )

    resolved: list[IdentityDecision] = []
    for decision in decisions:
        if decision.action != "unresolved" or any(
            (
                decision.candidate.role,
                decision.candidate.recruiting_project,
                decision.candidate.job_code,
            )
        ):
            resolved.append(decision)
            continue
        company_id = _company_identity(dictionaries, decision.candidate.company)
        nearby_keys = {
            other.application_key
            for other in decisions
            if other.application_key
            and other is not decision
            and _company_identity(dictionaries, other.candidate.company) == company_id
            and abs(
                other.event.source_received_at
                - decision.event.source_received_at
            )
            <= BATCH_CONTEXT_WINDOW
        }
        if len(nearby_keys) == 1:
            application_key = next(iter(nearby_keys))
            resolved.append(
                replace(
                    decision,
                    application_key=application_key,
                    action="batch_context_match",
                    resolution=ResolutionResult(
                        status="matched",
                        application_key=application_key,
                        confidence=0.8,
                        reason="unique-nearby-batch-context",
                        candidates=decision.resolution.candidates,
                    ),
                )
            )
        else:
            resolved.append(decision)
    return resolved
