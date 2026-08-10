from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import logging

from .application_registry import ApplicationRegistry, preview_progress_applications
from .config import (
    APPLICATIONS_DIR,
    DASHBOARD_FILE,
    DICTIONARIES_DIR,
    STATE_DB,
    TASKS_DIR,
    UNRESOLVED_DIR,
    Settings,
    ensure_directories,
)
from .credentials import load_credential
from .exporter import export_dashboard, import_checked_states
from .mail_reader import ImapReader
from .identity_dictionaries import load_identity_dictionaries
from .identity_pipeline import resolve_event_batch
from .identity_resolver import ResolutionResult
from .markdown_store import MarkdownTaskStore
from .models import ApplicationRecord, ParsedEvent
from .parser import PARSER_VERSION, SHANGHAI, parse_record
from .progress import export_progress, sync_current_applications_to_ledger
from .research import synchronize_research_state
from .state import StateStore
from .task_service import (
    critical_time,
    message_hash,
    legacy_application_id,
    task_from_event,
)
from .unresolved_store import UnresolvedStore, unresolved_from_decision


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanSummary:
    fetched: int
    skipped: int
    candidates: int
    tasks_updated: int
    parse_failed: int
    research_queued: int
    urgent: int
    exported: int
    shadow: bool
    preview: tuple[dict[str, object], ...] = ()
    identity_mode: str = "legacy"
    identity_matched: int = 0
    identity_new_applications: int = 0
    identity_unresolved: int = 0
    identity_conflicts: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


INITIAL_LOOKBACK_DAYS = 30
STALE_ACTION_DAYS = 7
STALE_EVENT_TYPES = {"assessment", "interview", "deadline"}


def _effective_lookback_days(
    settings: Settings,
    state: StateStore,
    requested_days: int | None,
    *,
    parser_changed: bool = False,
) -> int:
    if requested_days is not None:
        return requested_days
    if parser_changed or not state.has_successful_scan():
        return max(INITIAL_LOOKBACK_DAYS, settings.lookback_days)
    return settings.lookback_days


def _is_stale_attention(task, now: datetime) -> bool:
    return (
        task.status == "needs_review"
        and task.event_type in STALE_EVENT_TYPES
        and critical_time(task) is None
        and task.received_at < now - timedelta(days=STALE_ACTION_DAYS)
    )


def _resolution_applications(settings: Settings):
    records = {
        record.application_key: record
        for record in ApplicationRegistry(APPLICATIONS_DIR).all()
    }
    for record in preview_progress_applications(settings.progress_source):
        records.setdefault(record.application_key, record)
    return list(records.values())


def _company_key(dictionaries, company: str | None) -> str:
    return dictionaries.company_id(company) or (company or "unknown-company").casefold()


def _application_from_decision(
    decision,
    dictionaries,
    legacy_id: str,
) -> ApplicationRecord:
    candidate = decision.candidate
    return ApplicationRecord(
        application_key=decision.application_key,
        company_key=_company_key(dictionaries, candidate.company),
        company=candidate.company or "公司待确认",
        recruiting_project=candidate.recruiting_project,
        recruiting_year=candidate.recruiting_year,
        business_unit=candidate.business_unit,
        role=candidate.role,
        role_aliases=[],
        job_code=candidate.job_code,
        submitted_at=decision.event.source_received_at,
        status="active",
        source="mail",
        confirmed_by_user=False,
        identity_locked=False,
        legacy_application_ids=[legacy_id],
        identity_evidence=["explicit-application-mail"],
    )


def _legacy_id_for_key(
    application_key: str,
    registry: ApplicationRegistry,
    store: MarkdownTaskStore,
) -> str | None:
    task_ids = {
        task.application_id
        for task in store.all()
        if task.application_key == application_key
    }
    if len(task_ids) == 1:
        return next(iter(task_ids))
    if len(task_ids) > 1:
        return None
    record = registry.load(application_key)
    if record:
        legacy_ids = set(record.legacy_application_ids)
        if len(legacy_ids) == 1:
            return next(iter(legacy_ids))
        if len(legacy_ids) > 1:
            return None
    return legacy_application_id(application_key)


def _backfill_task_application_keys(
    registry: ApplicationRegistry,
    store: MarkdownTaskStore,
) -> int:
    legacy_candidates: dict[str, set[str]] = {}
    for record in registry.all(ignore_invalid=True):
        for legacy_id in record.legacy_application_ids:
            legacy_candidates.setdefault(legacy_id, set()).add(record.application_key)
    legacy_map = {
        legacy_id: next(iter(keys))
        for legacy_id, keys in legacy_candidates.items()
        if len(keys) == 1
    }
    updated = 0
    for task in store.all():
        if task.application_key:
            continue
        application_key = legacy_map.get(task.application_id)
        if not application_key:
            continue
        task.application_key = application_key
        store.save(task)
        updated += 1
    return updated


def _backfill_task_identity_fields(
    registry: ApplicationRegistry,
    store: MarkdownTaskStore,
) -> int:
    """Fill missing display identity from the canonical application record."""

    applications = {
        record.application_key: record
        for record in registry.all(ignore_invalid=True)
    }
    updated = 0
    for task in store.all():
        if not task.application_key:
            continue
        application = applications.get(task.application_key)
        if not application:
            continue
        changed = False
        if not task.role and application.role:
            task.role = application.role
            changed = True
        if not task.recruiting_project and application.recruiting_project:
            task.recruiting_project = application.recruiting_project
            changed = True
        if changed:
            store.save(task)
            updated += 1
    return updated


def _event_from_unresolved(record) -> ParsedEvent:
    """Rehydrate a privacy-safe pending record for identity reconciliation."""

    return ParsedEvent(
        company=record.company,
        role=record.role,
        recruiting_project=record.recruiting_project,
        event_type=record.event_type,
        stage=record.stage,
        round=record.round,
        title=record.title,
        start_at=record.start_at,
        end_at=record.end_at,
        deadline_at=record.deadline_at,
        source_message_id=f"unresolved:{record.id}",
        source_received_at=record.received_at,
        source_sender="",
        source_url=None,
        action_summary=record.action_summary,
        requirements=record.requirements,
        matched_keywords=(),
        confidence=record.confidence,
        change_type=record.change_type,  # type: ignore[arg-type]
    )


def _reconcile_pending_unresolved(
    settings: Settings,
    store: MarkdownTaskStore,
    state: StateStore,
    registry: ApplicationRegistry,
    dictionaries,
) -> tuple[int, int, int, int]:
    """Promote pending records when a stronger resolver rule becomes available.

    A message is marked processed at first sight to prevent duplicate IMAP
    work.  That used to make an unresolved first application permanent.  This
    small local pass retries only pending, privacy-safe metadata and can create
    a chain once a stable job code is available.
    """

    unresolved_store = UnresolvedStore(UNRESOLVED_DIR)
    pending = [item for item in unresolved_store.all() if item.status == "pending"]
    if not pending:
        return 0, 0, 0, 0

    events = [_event_from_unresolved(item) for item in pending]
    applications = registry.all(ignore_invalid=True)
    decisions = resolve_event_batch(events, applications, dictionaries)
    updated = identity_matched = identity_new = identity_conflicts = 0
    for item, event, decision in zip(pending, events, decisions, strict=True):
        if decision.action in {"unresolved", "conflict"}:
            # Refresh normalized candidate fields (including a recovered job
            # code) without changing the user's pending decision.
            unresolved_store.save(unresolved_from_decision(item.id, decision))
            if decision.action == "conflict":
                identity_conflicts += 1
            continue

        application_key = decision.application_key
        if not application_key:
            continue
        # Carry normalized identity fields into the materialized task too;
        # older unresolved files may have stored only the action summary.
        event = replace(
            event,
            role=decision.candidate.role or event.role,
            recruiting_project=(
                decision.candidate.recruiting_project
                or event.recruiting_project
            ),
        )
        resolved_legacy_id = _legacy_id_for_key(application_key, registry, store)
        if not resolved_legacy_id:
            identity_conflicts += 1
            continue

        application = registry.load(application_key)
        if decision.action == "new_application" and not application:
            application = _application_from_decision(
                decision,
                dictionaries,
                resolved_legacy_id,
            )
            registry.save(application)
            identity_new += 1
        else:
            identity_matched += 1
            if application and resolved_legacy_id not in application.legacy_application_ids:
                application.legacy_application_ids.append(resolved_legacy_id)
                application.legacy_application_ids.sort()
                registry.save(application)

        task = task_from_event(
            event,
            store,
            application_key=application_key,
            resolved_application_id=resolved_legacy_id,
        )
        store.save(task)
        unresolved_store.resolve(
            item.id,
            application_key=application_key,
            task_id=task.id,
        )
        state.mark_processed(item.id, task.id)
        updated += 1
    return updated, identity_matched, identity_new, identity_conflicts


def _scan_identity_preview(
    settings: Settings,
    *,
    days: int | None = None,
) -> ScanSummary:
    """Replay a bounded mailbox window without changing tasks or scan state."""
    ensure_directories()
    effective_days = days if days is not None else settings.lookback_days
    records = ImapReader(settings, load_credential()).fetch_since(effective_days)
    events = []
    parse_failed = 0
    for record in records:
        try:
            event = parse_record(record)
        except Exception:
            parse_failed += 1
            LOGGER.exception(
                "身份预览解析失败，已隔离 uid=%s",
                record.uid,
            )
            continue
        if event:
            events.append(event)
    dictionaries = load_identity_dictionaries(DICTIONARIES_DIR)
    decisions = resolve_event_batch(
        events,
        _resolution_applications(settings),
        dictionaries,
    )
    preview = tuple(decision.to_preview() for decision in decisions)
    return ScanSummary(
        fetched=len(records),
        skipped=0,
        candidates=len(events),
        tasks_updated=0,
        parse_failed=parse_failed,
        research_queued=0,
        urgent=0,
        exported=0,
        shadow=True,
        preview=preview,
        identity_mode="preview",
        identity_matched=sum(
            decision.action in {"matched", "batch_context_match"}
            for decision in decisions
        ),
        identity_new_applications=sum(
            decision.action == "new_application" for decision in decisions
        ),
        identity_unresolved=sum(
            decision.action == "unresolved" for decision in decisions
        ),
        identity_conflicts=sum(
            decision.action == "conflict" for decision in decisions
        ),
    )


def scan_once(
    settings: Settings,
    *,
    days: int | None = None,
    shadow: bool = False,
    identity_preview: bool = False,
) -> ScanSummary:
    if identity_preview:
        return _scan_identity_preview(settings, days=days)
    ensure_directories()
    store = MarkdownTaskStore(TASKS_DIR)
    store.backfill_completed_times()
    state = StateStore(STATE_DB)
    parser_changed = state.prepare_parser_version(PARSER_VERSION)
    run_id = state.begin_scan()
    fetched = skipped = candidates = updated = parse_failed = queued = urgent = exported = 0
    preview: list[dict[str, object]] = []
    identity_matched = identity_new = identity_unresolved = identity_conflicts = 0
    try:
        if settings.obsidian_enabled:
            import_checked_states(settings.obsidian_output, store)
        effective_days = _effective_lookback_days(
            settings,
            state,
            days,
            parser_changed=parser_changed,
        )
        records = ImapReader(settings, load_credential()).fetch_since(effective_days)
        pending_events: list[tuple[object, str, object]] = []
        for record in records:
            fetched += 1
            source_id = record.message_id or f"imap-uid:{record.uid}"
            source_hash = message_hash(source_id)
            if state.is_processed(source_hash):
                skipped += 1
                continue
            try:
                event = parse_record(record)
            except Exception as exc:
                # A malformed template must not block every later message. Keep
                # it unprocessed so a future parser update can retry it.
                parse_failed += 1
                LOGGER.exception(
                    "邮件解析失败，已隔离 uid=%s hash=%s error=%s",
                    record.uid,
                    source_hash[:12],
                    type(exc).__name__,
                )
                continue
            if event:
                candidates += 1
                pending_events.append((event, source_hash, record))
            elif not shadow:
                state.mark_processed(source_hash, None)

        dictionaries = load_identity_dictionaries(DICTIONARIES_DIR)
        registry = ApplicationRegistry(APPLICATIONS_DIR)
        if not shadow and settings.progress_source:
            registry.import_progress(settings.progress_source)
        if not shadow:
            _backfill_task_application_keys(registry, store)
            updated += _backfill_task_identity_fields(registry, store)
            (
                reconciled,
                reconciled_matched,
                reconciled_new,
                reconciled_conflicts,
            ) = _reconcile_pending_unresolved(
                settings,
                store,
                state,
                registry,
                dictionaries,
            )
            updated += reconciled
            identity_matched += reconciled_matched
            identity_new += reconciled_new
            identity_conflicts += reconciled_conflicts
        applications = (
            _resolution_applications(settings)
            if shadow
            else registry.all(ignore_invalid=True)
        )
        decisions = resolve_event_batch(
            [item[0] for item in pending_events],
            applications,
            dictionaries,
        )
        unresolved_store = UnresolvedStore(UNRESOLVED_DIR)
        for (event, source_hash, _record), decision in zip(
            pending_events,
            decisions,
            strict=True,
        ):
            if shadow:
                preview.append(decision.to_preview())
                continue
            if decision.action in {"unresolved", "conflict"}:
                unresolved_store.save(unresolved_from_decision(source_hash, decision))
                if decision.action == "conflict":
                    identity_conflicts += 1
                else:
                    identity_unresolved += 1
                state.mark_processed(source_hash, None)
                continue

            application_key = decision.application_key
            if not application_key:
                unresolved_store.save(unresolved_from_decision(source_hash, decision))
                identity_unresolved += 1
                state.mark_processed(source_hash, None)
                continue
            event = replace(
                event,
                role=decision.candidate.role or event.role,
                recruiting_project=(
                    decision.candidate.recruiting_project
                    or event.recruiting_project
                ),
            )
            resolved_legacy_id = _legacy_id_for_key(application_key, registry, store)
            if not resolved_legacy_id:
                conflict_decision = replace(
                    decision,
                    action="conflict",
                    resolution=ResolutionResult(
                        status="conflict",
                        application_key=None,
                        confidence=0.0,
                        reason="legacy-application-id-not-unique",
                        candidates=decision.resolution.candidates,
                        rule_version=decision.resolution.rule_version,
                    ),
                )
                unresolved_store.save(
                    unresolved_from_decision(source_hash, conflict_decision)
                )
                identity_conflicts += 1
                state.mark_processed(source_hash, None)
                continue

            record = registry.load(application_key)
            if decision.action == "new_application" and not record:
                record = _application_from_decision(
                    decision,
                    dictionaries,
                    resolved_legacy_id,
                )
                registry.save(record)
                identity_new += 1
            else:
                identity_matched += 1
                if record and resolved_legacy_id not in record.legacy_application_ids:
                    record.legacy_application_ids.append(resolved_legacy_id)
                    record.legacy_application_ids.sort()
                    registry.save(record)

            task = task_from_event(
                event,
                store,
                application_key=application_key,
                resolved_application_id=resolved_legacy_id,
            )
            store.save(task)
            updated += 1
            if task.priority == "urgent":
                urgent += 1
            state.mark_processed(source_hash, task.id)
        if not shadow:
            tasks = store.all()
            synchronize_research_state(
                tasks,
                settings.research_queue,
                store,
            )
            tasks = store.all()
            now = datetime.now().astimezone()
            for task in tasks:
                expires_at = task.end_at or task.deadline_at or task.start_at
                if (
                    expires_at
                    and expires_at < now
                    and task.status
                    not in {"done", "cancelled", "irrelevant", "expired"}
                ):
                    task.status = "expired"
                    store.save(task)
                elif _is_stale_attention(task, now):
                    task.status = "expired"
                    store.save(task)
            tasks = store.all()
            if settings.progress_enabled:
                try:
                    sync_current_applications_to_ledger(
                        tasks,
                        settings.progress_source,
                    )
                except PermissionError as exc:
                    LOGGER.warning(
                        "Progress ledger is temporarily locked; "
                        "mail scan will continue and retry next cycle: %s",
                        exc,
                    )
            export_dashboard(tasks, DASHBOARD_FILE, settings)
            if settings.obsidian_enabled:
                exported = export_dashboard(
                    tasks,
                    settings.obsidian_output,
                    settings,
                )
            if settings.progress_enabled:
                export_progress(
                    tasks,
                    settings.progress_output,
                    source_path=settings.progress_source,
                )
        summary = ScanSummary(
            fetched=fetched,
            skipped=skipped,
            candidates=candidates,
            tasks_updated=updated,
            parse_failed=parse_failed,
            research_queued=queued,
            urgent=urgent,
            exported=exported,
            shadow=shadow,
            preview=tuple(preview),
            identity_mode="registry",
            identity_matched=(
                sum(
                    decision.action in {"matched", "batch_context_match"}
                    for decision in decisions
                )
                if shadow
                else identity_matched
            ),
            identity_new_applications=(
                sum(decision.action == "new_application" for decision in decisions)
                if shadow
                else identity_new
            ),
            identity_unresolved=(
                sum(decision.action == "unresolved" for decision in decisions)
                if shadow
                else identity_unresolved
            ),
            identity_conflicts=(
                sum(decision.action == "conflict" for decision in decisions)
                if shadow
                else identity_conflicts
            ),
        )
        state.finish_scan(run_id, fetched=fetched, candidates=candidates)
        return summary
    except Exception as exc:
        state.finish_scan(
            run_id,
            fetched=fetched,
            candidates=candidates,
            error=str(exc),
        )
        raise
