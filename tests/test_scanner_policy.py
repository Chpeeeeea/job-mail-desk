from job_mail_desk.config import Settings
from datetime import datetime, timedelta

from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.scanner import (
    INITIAL_LOOKBACK_DAYS,
    _effective_lookback_days,
    _is_stale_attention,
)
from job_mail_desk.state import StateStore


def test_first_scan_uses_30_days_then_returns_to_configured_window(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    settings = Settings(lookback_days=3)
    assert _effective_lookback_days(settings, state, None) == INITIAL_LOOKBACK_DAYS
    assert _effective_lookback_days(settings, state, 12) == 12

    run_id = state.begin_scan()
    state.finish_scan(run_id, fetched=0, candidates=0)

    assert _effective_lookback_days(settings, state, None) == 3


def test_old_undated_assessment_leaves_attention_views() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=SHANGHAI)
    task = JobTask(
        id="1" * 24,
        application_id="2" * 20,
        company="样例公司",
        role="产品经理",
        recruiting_project=None,
        event_type="assessment",
        stage="人才测评",
        round=None,
        received_at=now - timedelta(days=8),
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="needs_review",
        change_type="new",
        source_message_hash="3" * 32,
        research_status="closed",
        confidence=1.0,
        title="人才测评",
        action_summary="完成测评",
    )

    assert _is_stale_attention(task, now)
    task.status = "confirmed"
    assert not _is_stale_attention(task, now)
