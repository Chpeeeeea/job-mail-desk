from datetime import datetime

from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.privacy import contains_sensitive_public_data, redact_text
from job_mail_desk.research import (
    build_request,
    close_requests_for_task,
    pending_requests,
    queue_request,
    request_states,
)


def task() -> JobTask:
    return JobTask(
        id="a" * 24,
        application_id="b" * 20,
        company="样例科技",
        role="产品经理",
        recruiting_project="2027校园招聘",
        event_type="assessment",
        stage="在线笔试",
        round=None,
        received_at=datetime(2026, 7, 30, 10, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 8, 2, 19, 0, tzinfo=SHANGHAI),
        end_at=datetime(2026, 8, 2, 21, 0, tzinfo=SHANGHAI),
        deadline_at=None,
        priority="high",
        status="needs_review",
        change_type="new",
        source_message_hash="c" * 32,
        research_status="not_queued",
        confidence=0.9,
        title="在线笔试通知",
        action_summary="请按时参加在线笔试",
        requirements=["请提前准备网络环境"],
        source_sender="招聘团队 <private@example.invalid>",
        source_url="https://private.example.invalid/exam?token=secret",
        is_ghost=True,
    )


def test_redaction_covers_private_identifiers() -> None:
    value = redact_text(
        "联系 private@example.invalid，手机13800138000，通行证：12345678"
    )
    assert "private@example.invalid" not in value
    assert "13800138000" not in value
    assert "12345678" not in value


def test_research_queue_contains_only_public_terms(tmp_path) -> None:
    item = task()
    request = build_request(item)
    assert request is not None
    queue = tmp_path / "queue.jsonl"
    assert queue_request(request, queue)
    payload = queue.read_text(encoding="utf-8")
    assert not contains_sensitive_public_data(payload)
    assert "private@" not in payload
    assert "https://" not in payload


def test_markdown_does_not_persist_mail_body(tmp_path) -> None:
    item = task()
    store = MarkdownTaskStore(tmp_path)
    path = store.save(item)
    content = path.read_text(encoding="utf-8")
    assert "FULL_PRIVATE_MAIL_BODY_MARKER" not in content
    assert "token=secret" in content  # Local task may retain its private source URL.


def test_legacy_completion_time_is_backfilled_and_marked_inferred(tmp_path) -> None:
    item = task()
    item.status = "done"
    item.updated_at = datetime(2026, 8, 3, 9, 30, tzinfo=SHANGHAI)
    store = MarkdownTaskStore(tmp_path)
    store.save(item)
    assert store.backfill_completed_times() == 1
    migrated = store.load(item.id)
    assert migrated is not None
    assert migrated.completed_at == item.updated_at
    assert migrated.completed_at_inferred is True
    content = store.path_for(item.id).read_text(encoding="utf-8")
    assert "完成：2026-08-03 09:30（由旧记录更新时间推定）" in content
    assert "结束：2026-08-02 21:00" in content


def test_completed_task_closes_pending_research(tmp_path) -> None:
    item = task()
    request = build_request(item)
    assert request is not None
    queue = tmp_path / "queue.jsonl"
    queue_request(request, queue)
    assert len(pending_requests(queue)) == 1
    assert close_requests_for_task(queue, item.id, reason="task_status:done") == 1
    assert pending_requests(queue) == []


def test_research_request_is_idempotent_across_later_scans(tmp_path) -> None:
    item = task()
    request = build_request(item)
    assert request is not None
    queue = tmp_path / "queue.jsonl"
    assert queue_request(request, queue)
    assert not queue_request(request, queue)
    assert len(queue.read_text(encoding="utf-8").splitlines()) == 1


def test_research_state_exposes_completed_result(tmp_path) -> None:
    item = task()
    request = build_request(item)
    assert request is not None
    payload = request.to_dict()
    payload["status"] = "completed"
    payload["result_path"] = "D:/research/研究草稿.md"
    queue = tmp_path / "queue.jsonl"
    queue.write_text(__import__("json").dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    state = request_states(queue)[item.id]
    assert state["status"] == "completed"
    assert state["result_path"].endswith("研究草稿.md")
