from datetime import datetime, timedelta

import job_mail_desk.dashboard as dashboard
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI


def test_completed_task_stays_in_dashboard_and_active_count_excludes_it(
    tmp_path,
    monkeypatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    task = JobTask(
        id="1" * 24,
        application_id="2" * 20,
        company="京东",
        role="TET 综合方向",
        recruiting_project=None,
        event_type="manual",
        stage="群面",
        round="群面",
        received_at=datetime(2026, 7, 31, 10, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 8, 6, 14, 0, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 6, 17, 0, tzinfo=SHANGHAI),
        deadline_at=None,
        priority="high",
        status="done",
        change_type="new",
        source_message_hash="manual",
        research_status="closed",
        confidence=1.0,
        title="参加京东群面",
        action_summary="参加京东群面",
    )
    store.save(task)
    monkeypatch.setattr(dashboard, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl")
    assert [item["id"] for item in payload["tasks"]] == [task.id]
    assert payload["tasks"][0]["status"] == "done"
    assert payload["tasks"][0]["view"] == "progress"
    assert payload["counts"]["list"] == 0
    assert payload["counts"]["today"] == 0
    assert payload["counts"]["progress"] == 1
    assert payload["progress"][0]["current_stage"] == "群面"


def test_snoozed_task_leaves_attention_views_but_keeps_event_time() -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=SHANGHAI)
    task = JobTask(
        id="3" * 24,
        application_id="4" * 20,
        company="京东",
        role="TET 综合方向",
        recruiting_project=None,
        event_type="manual",
        stage="群面",
        round="群面",
        received_at=now,
        start_at=now + timedelta(hours=4),
        end_at=None,
        deadline_at=None,
        priority="high",
        status="planned",
        change_type="new",
        source_message_hash="manual",
        research_status="closed",
        confidence=1.0,
        title="参加京东群面",
        action_summary="参加京东群面",
        source_url="https://example.com/notice",
        snoozed_until=now + timedelta(hours=2),
    )
    item = dashboard._task_payload(task, now)
    assert item["view"] == "snoozed"
    assert item["time"] == task.start_at.isoformat()
    assert item["snoozed_until"] == task.snoozed_until.isoformat()
    assert item["has_source"] is True


def test_dashboard_cache_reuses_unchanged_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    cache = tmp_path / "dashboard-cache.json"
    first = dashboard.cached_dashboard_payload(
        tmp_path / "research.jsonl",
        cache_path=cache,
    )

    def fail_if_recomputed(*_args, **_kwargs):
        raise AssertionError("unchanged dashboard should use cache")

    monkeypatch.setattr(dashboard, "dashboard_payload", fail_if_recomputed)
    second = dashboard.cached_dashboard_payload(
        tmp_path / "research.jsonl",
        cache_path=cache,
    )
    assert second == first
