from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .config import DASHBOARD_FILE, STATE_DB, TASKS_DIR, Settings, ensure_directories
from .credentials import load_credential
from .exporter import export_dashboard, import_checked_states
from .mail_reader import ImapReader
from .markdown_store import MarkdownTaskStore
from .parser import PARSER_VERSION, SHANGHAI, parse_record
from .progress import export_progress
from .research import build_request, queue_request, synchronize_research_state
from .state import StateStore
from .task_service import message_hash, task_from_event


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
        records = ImapReader(settings, load_credential()).fetch_since(days)
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
                    if settings.research_enabled:
                        request = build_request(task)
                        if request and queue_request(
                            request,
                            settings.research_queue,
                            store,
                        ):
                            queued += 1
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
