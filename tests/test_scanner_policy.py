from job_mail_desk.config import Settings
from datetime import datetime, timedelta

from job_mail_desk.models import JobTask, MailRecord, ParsedEvent
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.scanner import (
    _effective_lookback_days,
    _is_stale_attention,
)
from job_mail_desk import scanner
from job_mail_desk.state import StateStore
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.unresolved_store import UnresolvedStore


def test_normal_scan_uses_configured_window_even_for_new_or_changed_state(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    settings = Settings(lookback_days=3)
    assert _effective_lookback_days(settings, state, None) == 3
    assert _effective_lookback_days(settings, state, 12) == 12

    run_id = state.begin_scan()
    state.finish_scan(run_id, fetched=0, candidates=0)

    assert _effective_lookback_days(settings, state, None) == 3
    assert _effective_lookback_days(settings, state, None, parser_changed=True) == 3


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


def test_one_parser_failure_does_not_abort_the_mail_batch(tmp_path, monkeypatch) -> None:
    records = [
        MailRecord(
            uid="bad",
            subject="坏日期模板",
            message_id="<bad@example.invalid>",
            sender="样例招聘 <noreply@example.invalid>",
            received_at=datetime(2026, 8, 3, 9, 0, tzinfo=SHANGHAI),
            body="400-618-5106 服务时间 9:00-18:00",
        ),
        MailRecord(
            uid="good",
            subject="普通通知",
            message_id="<good@example.invalid>",
            sender="样例招聘 <noreply@example.invalid>",
            received_at=datetime(2026, 8, 3, 9, 1, tzinfo=SHANGHAI),
            body="普通邮件",
        ),
    ]

    class FakeReader:
        def __init__(self, settings, credential):
            pass

        def fetch_since(self, days):
            return records

    def fake_parse(record):
        if record.uid == "bad":
            raise ValueError("month must be in 1..12")
        return None

    monkeypatch.setattr(scanner, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(scanner, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(scanner, "DASHBOARD_FILE", tmp_path / "dashboard.md")
    monkeypatch.setattr(scanner, "ImapReader", FakeReader)
    monkeypatch.setattr(scanner, "load_credential", lambda: object())
    monkeypatch.setattr(scanner, "parse_record", fake_parse)

    summary = scanner.scan_once(Settings(), days=3)
    assert summary.fetched == 2
    assert summary.parse_failed == 1
    assert summary.candidates == 0

    repeated = scanner.scan_once(Settings(), days=3)
    assert repeated.fetched == 2
    assert repeated.parse_failed == 1
    assert repeated.skipped == 1


def test_identity_preview_batches_resolution_without_writing_state(
    tmp_path,
    monkeypatch,
) -> None:
    received = datetime(2026, 8, 4, 9, 0, tzinfo=SHANGHAI)
    records = [
        MailRecord(
            uid="receipt",
            subject="已收到申请",
            message_id="<receipt@example.invalid>",
            sender="campus@example.invalid",
            received_at=received,
            body="已收到申请",
        ),
        MailRecord(
            uid="jds",
            subject="JDS在线测评",
            message_id="<jds@example.invalid>",
            sender="campus@example.invalid",
            received_at=received + timedelta(minutes=8),
            body="JDS在线测评",
        ),
        MailRecord(
            uid="late-receipt",
            subject="已收到申请",
            message_id="<late@example.invalid>",
            sender="campus@example.invalid",
            received_at=received + timedelta(hours=6),
            body="已收到申请",
        ),
    ]

    class FakeReader:
        def __init__(self, settings, credential):
            pass

        def fetch_since(self, days):
            return records

    def fake_parse(record):
        explicit = record.uid == "jds"
        return ParsedEvent(
            company="京东",
            role="产品经理" if explicit else None,
            recruiting_project="JDS" if explicit else None,
            event_type="assessment" if explicit else "application",
            stage="在线测评" if explicit else "网申",
            round=None,
            title=record.subject,
            start_at=None,
            end_at=None,
            deadline_at=None,
            source_message_id=record.message_id,
            source_received_at=record.received_at,
            source_sender=record.sender,
            source_url=None,
            action_summary="等待后续",
            requirements=(),
            matched_keywords=(),
            confidence=0.9,
            change_type="new",
        )

    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 京东｜2027 JDS 产品经理｜已投递｜等待后续
- [x] 京东｜2027 TET 综合方向｜已投递｜等待后续
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(scanner, "APPLICATIONS_DIR", tmp_path / "applications")
    monkeypatch.setattr(scanner, "DICTIONARIES_DIR", tmp_path / "dictionaries")
    monkeypatch.setattr(scanner, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(scanner, "ImapReader", FakeReader)
    monkeypatch.setattr(scanner, "load_credential", lambda: object())
    monkeypatch.setattr(scanner, "parse_record", fake_parse)

    summary = scanner.scan_once(
        Settings(
            progress_source=ledger,
            obsidian_enabled=True,
            obsidian_output=tmp_path / "obsidian.md",
        ),
        days=3,
        identity_preview=True,
    )
    assert summary.identity_mode == "preview"
    assert summary.identity_matched == 2
    assert summary.identity_unresolved == 1
    assert summary.tasks_updated == 0
    assert summary.preview[0]["application_key"] == summary.preview[1][
        "application_key"
    ]
    assert summary.preview[2]["identity_action"] == "unresolved"
    assert not (tmp_path / "state.db").exists()
    assert not (tmp_path / "tasks").exists()


def test_registry_scan_groups_batch_receipt_and_persists_unresolved(
    tmp_path,
    monkeypatch,
) -> None:
    received = datetime(2026, 8, 4, 9, 0, tzinfo=SHANGHAI)
    records = [
        MailRecord(
            uid="receipt",
            subject="【京东校招】我们已收到你的申请，请及时关注后续进展",
            message_id="<receipt@example.invalid>",
            sender="campus@example.invalid",
            received_at=received,
            body="感谢你对京东校招的关注，我们已收到申请",
        ),
        MailRecord(
            uid="jds",
            subject="JDS 在线测评",
            message_id="<jds@example.invalid>",
            sender="campus@example.invalid",
            received_at=received + timedelta(minutes=8),
            body="产品经理 JDS 在线测评",
        ),
        MailRecord(
            uid="unknown",
            subject="网申成功提交",
            message_id="<unknown@example.invalid>",
            sender="campus@example.invalid",
            received_at=received + timedelta(hours=6),
            body="网申成功提交",
        ),
    ]

    class FakeReader:
        def __init__(self, settings, credential):
            pass

        def fetch_since(self, days):
            return records

    def fake_parse(record):
        if record.uid == "jds":
            role = "产品经理"
            project = "JDS"
            event_type = "assessment"
            stage = "在线测评"
        elif record.uid == "receipt":
            role = project = None
            event_type = "application"
            stage = "网申"
        else:
            role = project = None
            event_type = "application"
            stage = "网申"
        return ParsedEvent(
            company="京东" if record.uid != "unknown" else "样例公司",
            role=role,
            recruiting_project=project,
            event_type=event_type,
            stage=stage,
            round=None,
            title=record.subject,
            start_at=None,
            end_at=None,
            deadline_at=None,
            source_message_id=record.message_id,
            source_received_at=record.received_at,
            source_sender=record.sender,
            source_url=None,
            action_summary="等待后续",
            requirements=(),
            matched_keywords=(),
            confidence=0.9,
            change_type="new",
        )

    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        """# 台账

### 已投递或已进入流程
- [x] 京东｜2027 JDS 产品经理｜已投递｜等待后续
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(scanner, "APPLICATIONS_DIR", tmp_path / "applications")
    monkeypatch.setattr(scanner, "DICTIONARIES_DIR", tmp_path / "dictionaries")
    monkeypatch.setattr(scanner, "UNRESOLVED_DIR", tmp_path / "unresolved")
    monkeypatch.setattr(scanner, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(scanner, "DASHBOARD_FILE", tmp_path / "dashboard.md")
    monkeypatch.setattr(scanner, "ImapReader", FakeReader)
    monkeypatch.setattr(scanner, "load_credential", lambda: object())
    monkeypatch.setattr(scanner, "parse_record", fake_parse)

    summary = scanner.scan_once(Settings(progress_source=ledger), days=3)
    tasks = MarkdownTaskStore(tmp_path / "tasks").all()
    unresolved = UnresolvedStore(tmp_path / "unresolved").all()

    assert summary.identity_mode == "registry"
    assert summary.identity_matched == 2
    assert summary.identity_unresolved == 1
    assert len(tasks) == 2
    assert len({task.application_key for task in tasks}) == 1
    assert all(task.application_key for task in tasks)
    assert len(unresolved) == 1
    assert unresolved[0].company == "样例公司"

    repeated = scanner.scan_once(Settings(progress_source=ledger), days=3)
    assert repeated.skipped == 3
    assert len(MarkdownTaskStore(tmp_path / "tasks").all()) == 2
