from datetime import datetime

from job_mail_desk.models import MailRecord
from job_mail_desk.parser import SHANGHAI, parse_record
from job_mail_desk.task_service import critical_time, task_from_event
from job_mail_desk.markdown_store import MarkdownTaskStore


def mail(subject: str, body: str, message_id: str = "<sample@example.invalid>") -> MailRecord:
    return MailRecord(
        uid="1",
        subject=subject,
        message_id=message_id,
        sender="招聘团队 <noreply@example.invalid>",
        received_at=datetime(2026, 7, 29, 12, 0, tzinfo=SHANGHAI),
        body=body,
    )


def test_baidu_same_day_window() -> None:
    event = parse_record(
        mail(
            "【百度】2027校园招聘在线笔试通知",
            "笔试时间：2026年7月30日 19:00-21:00，请提前准备。",
        )
    )
    assert event is not None
    assert event.start_at == datetime(2026, 7, 30, 19, 0, tzinfo=SHANGHAI)
    assert event.end_at == datetime(2026, 7, 30, 21, 0, tzinfo=SHANGHAI)


def test_cross_date_window_uses_end_as_critical_time(tmp_path) -> None:
    event = parse_record(
        mail(
            "【海信】AI面试邀请",
            "AI面试有效期为2026年7月29日 10:20至2026年7月31日 10:20，请在有效期内完成。",
        )
    )
    assert event is not None
    task = task_from_event(event, MarkdownTaskStore(tmp_path))
    assert critical_time(task) == datetime(2026, 7, 31, 10, 20, tzinfo=SHANGHAI)


def test_resume_completion_24_hour_deadline() -> None:
    event = parse_record(
        mail(
            "邀请您完善简历信息-北京掌上先机网络科技有限公司（慧策旺店通）",
            (
                "感谢您投递北京掌上先机网络科技有限公司（慧策旺店通）储备销售主管，"
                "现邀请您完善您的简历信息。请在 2026-08-07 24:00 前，"
                "点击马上完善简历信息。招聘流程包括测试、笔试、面试和发放录用通知。"
            ),
        )
    )
    assert event is not None
    assert event.stage == "简历完善"
    assert event.event_type == "deadline"
    assert event.deadline_at == datetime(2026, 8, 8, 0, 0, tzinfo=SHANGHAI)
    assert event.start_at is None
    assert event.role == "储备销售主管"


def test_chinese_hour_minute_deadline() -> None:
    event = parse_record(
        mail(
            "【京东校招】2027 TET 综合面意向面试时间选择",
            "请务必在2026年08月01日 23点59分（北京时间）前反馈面试时间。",
        )
    )
    assert event is not None
    assert event.deadline_at == datetime(2026, 8, 1, 23, 59, tzinfo=SHANGHAI)
    assert event.start_at is None


def test_iflytek_validity_window_beats_conditional_rejection(tmp_path) -> None:
    record = mail(
        "【讯飞招聘】测评通知：科大讯飞邀请您参与校园招聘在线测评",
        (
            "现邀请您参加 AI产品经理 岗位的线上测评。"
            "若测评结果未通过或未及时作答，校招流程将结束。"
            "测评将于 2026年08月08日 12:35 失效。"
            "本次邀请于 2026年08月01日 12:35 生效，"
            "于 2026年08月08日 12:35 失效。"
        ),
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "科大讯飞"
    assert event.role == "AI产品经理"
    assert event.stage == "人才测评"
    assert event.event_type == "assessment"
    assert event.start_at == datetime(2026, 8, 1, 12, 35, tzinfo=SHANGHAI)
    assert event.end_at == datetime(2026, 8, 8, 12, 35, tzinfo=SHANGHAI)
    assert event.deadline_at is None
    task = task_from_event(event, MarkdownTaskStore(tmp_path))
    assert critical_time(task) == datetime(2026, 8, 8, 12, 35, tzinfo=SHANGHAI)
    assert task.status == "planned"


def test_footer_words_do_not_cancel_event() -> None:
    event = parse_record(
        mail(
            "【样例公司】在线笔试通知",
            "作弊将取消资格。如不想接收推广邮件可取消订阅。",
        )
    )
    assert event is not None
    assert event.change_type == "new"


def test_without_time_remains_unset() -> None:
    event = parse_record(
        mail("【深度路线】面试通知", "具体面试时间将另行通知。")
    )
    assert event is not None
    assert event.start_at is None
    assert event.deadline_at is None


def test_rejection_uses_generic_action_without_body_salutation() -> None:
    event = parse_record(
        mail(
            "【样例科技】应聘结果通知",
            "职位：产品经理 结果：不匹配 某某，你好，感谢你的投递。",
        )
    )
    assert event is not None
    assert event.stage == "未通过"
    assert "某某" not in event.action_summary
    assert event.requirements == ()


def test_rejection_is_not_left_as_an_actionable_todo(tmp_path) -> None:
    event = parse_record(
        mail("【样例科技】应聘结果通知", "职位：产品经理 结果：不匹配。")
    )
    assert event is not None
    task = task_from_event(event, MarkdownTaskStore(tmp_path))
    assert task.status == "done"


def test_reschedule_updates_same_task(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    first = parse_record(
        mail(
            "【样例公司】一面邀请",
            "面试时间：2026年8月2日 10:00，请准时参加。",
            "<first@example.invalid>",
        )
    )
    assert first is not None
    original = task_from_event(first, store)
    store.save(original)
    changed = parse_record(
        mail(
            "【样例公司】一面时间调整",
            "原面试时间调整为2026年8月3日 14:00，请准时参加。",
            "<changed@example.invalid>",
        )
    )
    assert changed is not None
    updated = task_from_event(changed, store)
    assert updated.id == original.id
    assert updated.start_at == datetime(2026, 8, 3, 14, 0, tzinfo=SHANGHAI)
    assert updated.change_type == "update"


def test_ignored_task_is_not_reactivated_by_later_scan(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    first = parse_record(
        mail(
            "【样例公司】招聘通知",
            "欢迎关注2027校园招聘。",
            "<ignored@example.invalid>",
        )
    )
    assert first is not None
    ignored = task_from_event(first, store)
    ignored.status = "irrelevant"
    store.save(ignored)
    rescanned = task_from_event(first, store)
    assert rescanned.id == ignored.id
    assert rescanned.status == "irrelevant"


def test_ghost_application_is_reused_across_stages(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    assessment = parse_record(
        mail(
            "【样例科技】2027校园招聘在线笔试",
            "笔试时间：2026年8月2日 10:00。",
            "<assessment@example.invalid>",
        )
    )
    assert assessment is not None
    first = task_from_event(assessment, store)
    store.save(first)
    interview = parse_record(
        mail(
            "【样例科技】2027校园招聘一面邀请",
            "应聘岗位：产品经理\n面试时间：2026年8月5日 15:00。",
            "<interview@example.invalid>",
        )
    )
    assert interview is not None
    second = task_from_event(interview, store)
    assert first.application_id == second.application_id
