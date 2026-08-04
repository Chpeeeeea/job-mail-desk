from datetime import datetime, timedelta

from job_mail_desk.identity_dictionaries import load_identity_dictionaries
from job_mail_desk.identity_pipeline import resolve_event_batch
from job_mail_desk.models import ApplicationRecord, ParsedEvent
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.unresolved_store import (
    UnresolvedStore,
    unresolved_from_decision,
)


NOW = datetime(2026, 8, 4, 9, 0, tzinfo=SHANGHAI)


def event(
    *,
    company: str = "京东",
    role: str | None = None,
    project: str | None = None,
    event_type: str = "application",
    stage: str = "网申",
    received_at: datetime = NOW,
    action: str = "等待后续",
    title: str = "招聘通知",
) -> ParsedEvent:
    return ParsedEvent(
        company=company,
        role=role,
        recruiting_project=project,
        event_type=event_type,
        stage=stage,
        round=None,
        title=title,
        start_at=None,
        end_at=None,
        deadline_at=None,
        source_message_id=f"<{received_at.timestamp()}-{role}-{project}@example.invalid>",
        source_received_at=received_at,
        source_sender="noreply@example.invalid",
        source_url=None,
        action_summary=action,
        requirements=(),
        matched_keywords=(),
        confidence=0.9,
        change_type="new",
    )


def application(
    key: str,
    *,
    project: str,
    role: str,
) -> ApplicationRecord:
    return ApplicationRecord(
        application_key=key,
        company_key="jd",
        company="京东",
        recruiting_project=project,
        recruiting_year=2027,
        business_unit=None,
        role=role,
        role_aliases=[],
        job_code=None,
        submitted_at=NOW,
        status="active",
        source="test",
        confirmed_by_user=True,
        identity_locked=True,
    )


def test_generic_receipt_stays_unresolved_when_jds_and_tet_both_exist() -> None:
    decisions = resolve_event_batch(
        [event()],
        [
            application("app-jds", project="JDS", role="产品经理"),
            application("app-tet", project="TET", role="TET综合方向"),
        ],
        load_identity_dictionaries(),
    )
    assert decisions[0].action == "unresolved"
    assert decisions[0].application_key is None


def test_generic_receipt_uses_unique_nearby_explicit_batch_context() -> None:
    receipt = event(received_at=NOW)
    explicit = event(
        role="产品经理",
        project="JDS",
        event_type="assessment",
        stage="在线测评",
        received_at=NOW + timedelta(minutes=8),
    )
    decisions = resolve_event_batch(
        [receipt, explicit],
        [application("app-jds", project="JDS", role="产品经理")],
        load_identity_dictionaries(),
    )
    assert decisions[1].action == "matched"
    assert decisions[0].action == "batch_context_match"
    assert decisions[0].application_key == "app-jds"


def test_explicit_application_can_create_provisional_identity() -> None:
    decisions = resolve_event_batch(
        [event(company="帆软", role="产品经理")],
        [],
        load_identity_dictionaries(),
    )
    assert decisions[0].action == "new_application"
    assert decisions[0].application_key.startswith("app-")


def test_reviewed_receipt_template_cannot_create_application() -> None:
    decision = resolve_event_batch(
        [event(company="帆软", role="产品经理", title="恭喜您网申成功提交")],
        [],
        load_identity_dictionaries(),
    )[0]
    assert decision.candidate.template_id == "generic-application-success"
    assert decision.action == "unresolved"


def test_project_codes_and_business_unit_suffixes_are_normalized() -> None:
    jds = event(role=None, project="JDS · 2027校园招聘", event_type="assessment")
    tet = event(role="TET 综合方向", project="2027校园招聘", event_type="assessment")
    leihuo = event(
        company="网易游戏",
        role="游戏 AI 产品经理",
        project="雷火事业群 · 2027校园招聘",
        event_type="assessment",
    )
    from job_mail_desk.identity_pipeline import identity_candidate_from_event

    assert identity_candidate_from_event(jds).recruiting_project == "JDS"
    assert identity_candidate_from_event(tet).recruiting_project == "TET"
    candidate = identity_candidate_from_event(leihuo)
    assert candidate.recruiting_project == "雷火事业群"
    assert candidate.business_unit == "雷火事业群"


def test_assessment_with_long_garbage_role_cannot_create_application() -> None:
    garbage = event(
        company="样例集团",
        role="岗位名称：实施工程师；专业要求：请点击官网进行修改" * 8,
        event_type="application",
        stage="测评",
    )
    decision = resolve_event_batch(
        [garbage],
        [],
        load_identity_dictionaries(),
    )[0]
    assert decision.action == "unresolved"


def test_existing_candidate_prevents_duplicate_new_application() -> None:
    incoming = event(company="京东", role="陌生岗位", stage="网申")
    decision = resolve_event_batch(
        [incoming],
        [application("app-jds", project="JDS", role="产品经理")],
        load_identity_dictionaries(),
    )[0]
    assert decision.action == "unresolved"
    assert decision.application_key is None


def test_unresolved_store_is_idempotent_and_excludes_private_fields(tmp_path) -> None:
    decision = resolve_event_batch(
        [
            event(
                company="京东",
                action=(
                    "联系 candidate@example.com，手机号 13800138000，"
                    "打开 https://example.com/private?token=secret"
                ),
            )
        ],
        [
            application("app-jds", project="JDS", role="产品经理"),
            application("app-tet", project="TET", role="TET综合方向"),
        ],
        load_identity_dictionaries(),
    )[0]
    store = UnresolvedStore(tmp_path)
    record = unresolved_from_decision("a" * 32, decision)
    first = store.save(record)
    second = store.save(record)
    assert first == second
    assert len(store.all()) == 1
    content = first.read_text(encoding="utf-8")
    assert "candidate@example.com" not in content
    assert "13800138000" not in content
    assert "https://" not in content
    assert "secret" not in content
    assert decision.event.source_sender not in content
    resolved = store.resolve(
        record.id,
        application_key="app-jds",
        task_id="task-1",
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_application_key == "app-jds"
    assert resolved.resolved_task_id == "task-1"
