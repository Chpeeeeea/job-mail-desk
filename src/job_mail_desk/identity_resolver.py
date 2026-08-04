from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .identity_dictionaries import IdentityDictionaries
from .models import ApplicationRecord
from .normalization import role_key


ResolutionStatus = Literal["matched", "unresolved", "conflict"]


@dataclass(frozen=True)
class IdentityCandidate:
    company: str | None
    role: str | None = None
    recruiting_project: str | None = None
    recruiting_year: int | None = None
    business_unit: str | None = None
    job_code: str | None = None
    legacy_application_id: str | None = None
    template_id: str | None = None


@dataclass(frozen=True)
class CandidateScore:
    application_key: str
    score: int
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionResult:
    status: ResolutionStatus
    application_key: str | None
    confidence: float
    reason: str
    candidates: tuple[CandidateScore, ...]
    rule_version: str = "identity-registry-v1"


class IdentityResolver:
    def __init__(self, dictionaries: IdentityDictionaries) -> None:
        self.dictionaries = dictionaries

    @staticmethod
    def _same_text(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False
        return role_key(left) == role_key(right)

    def _company_id_for_record(self, record: ApplicationRecord) -> str | None:
        return self.dictionaries.company_id(record.company)

    def _score(
        self,
        candidate: IdentityCandidate,
        record: ApplicationRecord,
    ) -> CandidateScore | None:
        candidate_company = self.dictionaries.company_id(candidate.company)
        record_company = self._company_id_for_record(record)
        if candidate_company:
            if record_company != candidate_company:
                return None
        elif candidate.company and not self._same_text(
            candidate.company,
            record.company,
        ):
            return None

        evidence: list[str] = []
        conflicts: list[str] = []
        score = 0
        if candidate_company and candidate_company == record_company:
            evidence.append("company")
            score += 5

        candidate_code = candidate.job_code.upper() if candidate.job_code else None
        record_code = record.job_code.upper() if record.job_code else None
        if candidate_code and record_code:
            if candidate_code != record_code:
                conflicts.append("job-code")
            else:
                evidence.append("job-code")
                score += 100

        if (
            candidate.legacy_application_id
            and candidate.legacy_application_id in record.legacy_application_ids
        ):
            evidence.append("legacy-application-id")
            score += 100

        candidate_program = self.dictionaries.program_id(
            candidate_company,
            candidate.recruiting_project,
        )
        record_program = self.dictionaries.program_id(
            record_company,
            record.recruiting_project,
        )
        if candidate_program and record_program:
            if candidate_program != record_program:
                conflicts.append("recruiting-project")
            else:
                evidence.append("recruiting-project")
                score += 45
        elif candidate.recruiting_project and record.recruiting_project:
            if not self._same_text(
                candidate.recruiting_project,
                record.recruiting_project,
            ):
                conflicts.append("recruiting-project")
            else:
                evidence.append("recruiting-project-text")
                score += 35

        if candidate.recruiting_year and record.recruiting_year:
            if candidate.recruiting_year != record.recruiting_year:
                conflicts.append("recruiting-year")
            else:
                evidence.append("recruiting-year")
                score += 20

        if candidate.business_unit and record.business_unit:
            if not self._same_text(candidate.business_unit, record.business_unit):
                conflicts.append("business-unit")
            else:
                evidence.append("business-unit")
                score += 35

        candidate_role = self.dictionaries.role_id(candidate.role)
        record_role = self.dictionaries.role_id(record.role)
        if candidate_role and record_role and candidate_role == record_role:
            evidence.append("role")
            score += 20
        elif self._same_text(candidate.role, record.role):
            evidence.append("role-text")
            score += 15

        return CandidateScore(
            application_key=record.application_key,
            score=score,
            evidence=tuple(evidence),
            conflicts=tuple(conflicts),
        )

    def resolve(
        self,
        candidate: IdentityCandidate,
        applications: list[ApplicationRecord],
    ) -> ResolutionResult:
        scored = [
            result
            for record in applications
            if (result := self._score(candidate, record)) is not None
        ]
        non_conflicting = [result for result in scored if not result.conflicts]
        ranked = sorted(non_conflicting, key=lambda item: item.score, reverse=True)
        conflicts = sorted(
            (result for result in scored if result.conflicts),
            key=lambda item: item.score,
            reverse=True,
        )

        strong = [
            result
            for result in ranked
            if "job-code" in result.evidence
            or "legacy-application-id" in result.evidence
        ]
        if len(strong) == 1:
            return ResolutionResult(
                status="matched",
                application_key=strong[0].application_key,
                confidence=1.0,
                reason="strong-identifier",
                candidates=tuple(ranked + conflicts),
            )
        if len(strong) > 1:
            return ResolutionResult(
                status="conflict",
                application_key=None,
                confidence=0.0,
                reason="strong-identifier-not-unique",
                candidates=tuple(ranked + conflicts),
            )

        deterministic = [
            result
            for result in ranked
            if (
                "recruiting-project" in result.evidence
                or "recruiting-project-text" in result.evidence
            )
            or (
                "business-unit" in result.evidence
                and (
                    "role" in result.evidence
                    or "role-text" in result.evidence
                )
            )
            or (
                "company" in result.evidence
                and (
                    "role" in result.evidence
                    or "role-text" in result.evidence
                )
            )
        ]
        if len(deterministic) == 1:
            evidence = deterministic[0].evidence
            if "recruiting-project" in evidence or "recruiting-project-text" in evidence:
                reason = "unique-project-combination"
            elif "business-unit" in evidence:
                reason = "unique-business-unit-role"
            else:
                reason = "unique-company-role"
            return ResolutionResult(
                status="matched",
                application_key=deterministic[0].application_key,
                confidence=0.9 if reason != "unique-company-role" else 0.85,
                reason=reason,
                candidates=tuple(ranked + conflicts),
            )
        if conflicts and not ranked:
            return ResolutionResult(
                status="conflict",
                application_key=None,
                confidence=0.0,
                reason="hard-identity-conflict",
                candidates=tuple(conflicts),
            )
        return ResolutionResult(
            status="unresolved",
            application_key=None,
            confidence=0.0,
            reason=(
                "multiple-candidates"
                if len(ranked) > 1
                else "insufficient-identity-evidence"
            ),
            candidates=tuple(ranked + conflicts),
        )
