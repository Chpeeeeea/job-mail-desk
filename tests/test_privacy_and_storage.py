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


def test_completed_task_closes_pending_research(tmp_path) -> None:
    item = task()
    request = build_request(item)
    assert request is not None
    queue = tmp_path / "queue.jsonl"
    queue_request(request, queue)
    assert len(pending_requests(queue)) == 1
    assert close_requests_for_task(queue, item.id, reason="task_status:done") == 1
    assert pending_requests(queue) == []
