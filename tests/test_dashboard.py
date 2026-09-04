from datetime import datetime, timedelta

import job_mail_desk.dashboard as dashboard
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.unresolved_store import UnresolvedRecord, UnresolvedStore


def test_completed_stage_stays_visible_while_application_waits_for_result(
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
    assert payload["tasks"][0]["actionable"] is False
    assert payload["counts"]["list"] == 0
    assert payload["counts"]["today"] == 0
    assert payload["counts"]["progress"] == 1
    assert payload["progress"][0]["current_stage"] == "2026-08-06 群面已完成，等待结果"
    assert payload["progress"][0]["application_state"] == "active"
    assert payload["progress"][0]["active"] is True


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


def test_needs_review_without_time_stays_out_of_todo_list() -> None:
    now = datetime(2026, 8, 1, 10, 0, tzinfo=SHANGHAI)
    task = JobTask(
        id="8" * 24,
        application_id="9" * 20,
        company="样例公司",
        role="管培生",
        recruiting_project=None,
        event_type="application",
        stage="简历筛选",
        round=None,
        received_at=now,
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="needs_review",
        change_type="new",
        source_message_hash="a" * 32,
        research_status="closed",
        confidence=1.0,
        title="简历筛选中",
        action_summary="等待后续通知",
    )

    item = dashboard._task_payload(task, now)
    assert item["view"] == "review"
    assert item["actionable"] is False


def test_recently_completed_task_stays_in_review_for_two_days() -> None:
    now = datetime(2026, 8, 31, 20, 0, tzinfo=SHANGHAI)
    task = JobTask(
        id="a" * 24,
        application_id="b" * 20,
        company="样例公司",
        role="AI 产品经理",
        recruiting_project=None,
        event_type="interview",
        stage="AI 面试",
        round=None,
        received_at=now - timedelta(hours=3),
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="done",
        change_type="new",
        source_message_hash="c" * 32,
        research_status="closed",
        confidence=1.0,
        title="AI 面试通知",
        action_summary="确认 AI 面试安排",
        completed_at=now - timedelta(hours=1),
    )

    item = dashboard._task_payload(task, now)

    assert item["recently_handled"] is True
    assert item["view"] == "review"
    assert item["actionable"] is False
    assert item["remaining"] == "已完成"


def test_completed_task_leaves_review_after_two_days() -> None:
    now = datetime(2026, 8, 31, 20, 0, tzinfo=SHANGHAI)
    task = JobTask(
        id="d" * 24,
        application_id="e" * 20,
        company="样例公司",
        role="AI 产品经理",
        recruiting_project=None,
        event_type="interview",
        stage="AI 面试",
        round=None,
        received_at=now - timedelta(days=4),
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="done",
        change_type="new",
        source_message_hash="f" * 32,
        research_status="closed",
        confidence=1.0,
        title="AI 面试通知",
        action_summary="确认 AI 面试安排",
        completed_at=now - timedelta(days=2),
    )

    item = dashboard._task_payload(task, now)

    assert item["recently_handled"] is False
    assert item["view"] == "progress"


def test_recently_ignored_task_remains_visible_then_expires(
    tmp_path,
    monkeypatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    task = JobTask(
        id="1" * 24,
        application_id="2" * 20,
        company="样例公司",
        role="产品经理",
        recruiting_project=None,
        event_type="assessment",
        stage="人才测评",
        round=None,
        received_at=datetime.now(SHANGHAI),
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="irrelevant",
        change_type="new",
        source_message_hash="3" * 32,
        research_status="closed",
        confidence=1.0,
        title="人才测评通知",
        action_summary="完成人才测评",
        updated_at=datetime.now(SHANGHAI) - timedelta(hours=1),
    )
    store.save(task)
    monkeypatch.setattr(dashboard, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(dashboard, "UNRESOLVED_DIR", tmp_path / "unresolved")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", tmp_path / "applications")

    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl")

    assert payload["tasks"][0]["status"] == "irrelevant"
    assert payload["tasks"][0]["view"] == "review"
    assert payload["tasks"][0]["remaining"] == "已忽略"
    assert payload["counts"]["review"] == 0


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


def test_expired_task_is_kept_in_todo_and_progress(
    tmp_path,
    monkeypatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    task = JobTask(
        id="5" * 24,
        application_id="6" * 20,
        company="样例公司",
        role="产品经理",
        recruiting_project=None,
        event_type="assessment",
        stage="在线笔试",
        round=None,
        received_at=datetime(2026, 7, 20, 10, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 7, 21, 10, 0, tzinfo=SHANGHAI),
        end_at=None,
        deadline_at=None,
        priority="normal",
        status="expired",
        change_type="new",
        source_message_hash="7" * 32,
        research_status="closed",
        confidence=1.0,
        title="已过期笔试",
        action_summary="参加在线笔试",
    )
    store.save(task)
    monkeypatch.setattr(dashboard, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")

    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl")
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["status"] == "expired"
    assert payload["tasks"][0]["actionable"] is True
    assert payload["counts"]["list"] == 1
    assert payload["progress"][0]["current_stage"] == "2026-07-21 在线笔试已过期 · 待确认"
    assert payload["progress"][0]["application_state"] == "expired"


def test_unresolved_items_share_the_review_count(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(dashboard, "UNRESOLVED_DIR", tmp_path / "unresolved")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", tmp_path / "applications")
    record = UnresolvedRecord(
        id="a" * 32,
        status="pending",
        resolution_status="unresolved",
        reason="multiple-candidates",
        company="样例公司",
        role=None,
        recruiting_project=None,
        event_type="assessment",
        stage="在线笔试",
        round=None,
        received_at=datetime(2026, 8, 8, 8, 0, tzinfo=SHANGHAI),
        start_at=None,
        end_at=None,
        deadline_at=None,
        action_summary="确认申请归属",
        title="笔试通知",
        requirements=(),
        confidence=0.8,
        change_type="new",
        candidate_application_keys=(),
        resolved_application_key=None,
        resolved_task_id=None,
        rule_version="identity-registry-v1",
    )
    UnresolvedStore(tmp_path / "unresolved").save(record)

    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl")
    assert payload["counts"]["review"] == 1
    assert payload["unresolved"][0]["attention_type"] == "unresolved_identity"


def test_terminal_ledger_status_removes_task_from_action_views(
    tmp_path,
    monkeypatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    task = JobTask(
        id="c" * 24,
        application_id="d" * 20,
        application_key="app-1234567890abcdef1234",
        company="旧企业",
        role="旧岗位",
        recruiting_project=None,
        event_type="interview",
        stage="面试",
        round=None,
        received_at=datetime(2026, 8, 8, 8, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 8, 9, 14, 0, tzinfo=SHANGHAI),
        end_at=None,
        deadline_at=None,
        priority="high",
        status="planned",
        change_type="new",
        source_message_hash="e" * 32,
        research_status="closed",
        confidence=1.0,
        title="面试通知",
        action_summary="参加面试",
    )
    store.save(task)
    ledger = tmp_path / "台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 新企业｜新岗位｜**未通过**｜停止跟进 <!-- jobmaildesk:application:app-1234567890abcdef1234 -->
### 当前优先待投
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(dashboard, "UNRESOLVED_DIR", tmp_path / "unresolved")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", tmp_path / "applications")

    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl", ledger)
    assert payload["tasks"][0]["company"] == "新企业"
    assert payload["tasks"][0]["role"] == "新岗位"
    assert payload["tasks"][0]["view"] == "progress"
    assert payload["tasks"][0]["actionable"] is False
    assert payload["counts"]["today"] == 0


def test_offer_ledger_status_removes_task_from_action_views(
    tmp_path,
    monkeypatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    task = JobTask(
        id="f" * 24,
        application_id="1" * 20,
        application_key="app-offer-dashboard-1234",
        company="帆软",
        role="产品经理",
        recruiting_project=None,
        event_type="interview",
        stage="终面",
        round="终面",
        received_at=datetime(2026, 9, 1, 8, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 9, 1, 10, 0, tzinfo=SHANGHAI),
        end_at=None,
        deadline_at=None,
        priority="high",
        status="done",
        change_type="new",
        source_message_hash="2" * 32,
        research_status="closed",
        confidence=1.0,
        title="终面",
        action_summary="参加终面",
        completed_at=datetime(2026, 9, 1, 12, 0, tzinfo=SHANGHAI),
    )
    store.save(task)
    ledger = tmp_path / "台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 帆软｜产品经理｜**2026-09-04 已 Offer**｜等待入职 <!-- jobmaildesk:application:app-offer-dashboard-1234 -->
### 当前优先待投
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard, "TASKS_DIR", tasks_dir)
    monkeypatch.setattr(dashboard, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(dashboard, "UNRESOLVED_DIR", tmp_path / "unresolved")
    monkeypatch.setattr(dashboard, "APPLICATIONS_DIR", tmp_path / "applications")

    payload = dashboard.dashboard_payload(tmp_path / "research.jsonl", ledger)
    assert payload["progress"][0]["application_state"] == "offered"
    assert payload["tasks"][0]["view"] == "progress"
    assert payload["tasks"][0]["actionable"] is False
    assert payload["counts"]["today"] == 0
