from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from .config import DASHBOARD_FILE, STATE_DB, TASKS_DIR, Settings, ensure_directories
from .credentials import load_credential
from .exporter import export_dashboard, import_checked_states
from .mail_reader import ImapReader
from .markdown_store import MarkdownTaskStore
from .parser import PARSER_VERSION, SHANGHAI, parse_record
from .progress import export_progress
from .research import synchronize_research_state
from .state import StateStore
from .task_service import critical_time, message_hash, task_from_event


@dataclass(frozen=True)
class ScanSummary:
    fetched: int
    skipped: int
    candidates: int
    tasks_updated: int
    research_queued: int
    urgent: int
    exported: int
    shadow: bool
    preview: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


INITIAL_LOOKBACK_DAYS = 30
STALE_ACTION_DAYS = 7
STALE_EVENT_TYPES = {"assessment", "interview", "deadline"}


def _effective_lookback_days(
    settings: Settings,
    state: StateStore,
    requested_days: int | None,
) -> int:
    if requested_days is not None:
        return requested_days
    if not state.has_successful_scan():
        return max(INITIAL_LOOKBACK_DAYS, settings.lookback_days)
    return settings.lookback_days


def _is_stale_attention(task, now: datetime) -> bool:
    return (
        task.status == "needs_review"
        and task.event_type in STALE_EVENT_TYPES
        and critical_time(task) is None
        and task.received_at < now - timedelta(days=STALE_ACTION_DAYS)
    )


def scan_once(
    settings: Settings,
    *,
    days: int | None = None,
    shadow: bool = False,
) -> ScanSummary:
    ensure_directories()
    store = MarkdownTaskStore(TASKS_DIR)
    state = StateStore(STATE_DB)
    state.prepare_parser_version(PARSER_VERSION)
    run_id = state.begin_scan()
    fetched = skipped = candidates = updated = queued = urgent = exported = 0
    preview: list[dict[str, object]] = []
    try:
        if settings.obsidian_enabled:
            import_checked_states(settings.obsidian_output, store)
        effective_days = _effective_lookback_days(settings, state, days)
        records = ImapReader(settings, load_credential()).fetch_since(effective_days)
        for record in records:
            fetched += 1
            source_id = record.message_id or f"imap-uid:{record.uid}"
            source_hash = message_hash(source_id)
            if state.is_processed(source_hash):
                skipped += 1
                continue
            event = parse_record(record)
            task_identifier = None
            if event:
                candidates += 1
                task = task_from_event(event, store)
                task_identifier = task.id
                if shadow:
                    preview.append(
                        {
                            "company": task.company,
                            "role": task.role,
                            "project": task.recruiting_project,
                            "stage": task.stage,
                            "round": task.round,
                            "start_at": task.start_at.isoformat()
                            if task.start_at
                            else None,
                            "end_at": task.end_at.isoformat()
                            if task.end_at
                            else None,
                            "deadline_at": task.deadline_at.isoformat()
                            if task.deadline_at
                            else None,
                            "change_type": task.change_type,
                            "confidence": task.confidence,
                        }
                    )
                if not shadow:
                    store.save(task)
                    updated += 1
                    if task.priority == "urgent":
                        urgent += 1
                    # Core never creates public research requests. Research is
                    # an external opt-in extension and cannot block mail sync.
            if not shadow:
                state.mark_processed(source_hash, task_identifier)
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
            research_queued=queued,
            urgent=urgent,
            exported=exported,
            shadow=shadow,
            preview=tuple(preview),
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
