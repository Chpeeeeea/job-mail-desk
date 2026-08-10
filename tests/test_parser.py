from datetime import datetime

from job_mail_desk.models import MailRecord
from job_mail_desk.parser import SHANGHAI, parse_record
from job_mail_desk.task_service import application_id, critical_time, task_from_event
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


def test_seasonal_campus_heading_extracts_identity_without_fabricating_time() -> None:
    event = parse_record(
        mail(
            "基恩士2027秋季校园招聘：销售工程师/销售岗位",
            "简历已优先进入初筛阶段，面试环节预计将于8月统一启动。",
        )
    )
    assert event is not None
    assert event.company == "基恩士"
    assert event.role == "销售工程师/销售"
    assert event.recruiting_project == "2027校园招聘"
    assert event.stage == "简历筛选"
    assert event.start_at is None
    assert event.end_at is None
    assert event.deadline_at is None


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


def test_relative_hours_deadline_uses_received_time() -> None:
    record = MailRecord(
        uid="relative-72",
        subject="校园招聘测评邀请",
        message_id="<relative-72@example.com>",
        sender="样例公司招聘 <hr@example.com>",
        received_at=datetime(2026, 7, 24, 19, 4, tzinfo=SHANGHAI),
        body="请您务必于收到本邮件后的72小时内完成在线测评。",
    )

    event = parse_record(record)
    assert event is not None
    assert event.deadline_at == datetime(2026, 7, 27, 19, 4, tzinfo=SHANGHAI)


def test_jd_jds_assessment_has_separate_project_and_relative_deadline() -> None:
    record = MailRecord(
        uid="jd-jds-assessment",
        subject="【京东校招】2027 JDS测评通知",
        message_id="<jd-jds-assessment@example.invalid>",
        sender="京东校招 <hr@example.invalid>",
        received_at=datetime(2026, 8, 3, 18, 18, tzinfo=SHANGHAI),
        body="建议您在48小时内完成在线测评，请及时关注后续进展。",
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "京东"
    assert event.recruiting_project == "JDS · 2027校园招聘"
    assert event.stage == "人才测评"
    assert event.deadline_at == datetime(2026, 8, 5, 18, 18, tzinfo=SHANGHAI)


def test_jd_application_acknowledgement_is_application() -> None:
    event = parse_record(
        MailRecord(
            uid="jd-jds-application",
            subject="【京东校招】我们已收到你的申请，请及时关注后续进展",
            message_id="<jd-jds-application@example.invalid>",
            sender="京东校招 <hr@example.invalid>",
            received_at=datetime(2026, 8, 3, 18, 0, tzinfo=SHANGHAI),
            body="感谢申请京东2027 JDS项目，请及时关注后续进展。",
        )
    )
    assert event is not None
    assert event.recruiting_project == "JDS · 2027校园招聘"
    assert event.stage == "网申"
    assert event.event_type == "application"


def test_jd_tet_subject_is_not_relabelled_by_jds_footer() -> None:
    event = parse_record(
        MailRecord(
            uid="jd-tet-footer",
            subject="【京东校招】2027 TET测评通知",
            message_id="<jd-tet-footer@example.invalid>",
            sender="京东校招 <hr@example.invalid>",
            received_at=datetime(2026, 7, 8, 16, 10, tzinfo=SHANGHAI),
            body=(
                "请完成在线测评。注意：投递JD YOUNG/JDS/TET/TGT中的多个项目，"
                "只需作答一次测评。"
            ),
        )
    )
    assert event is not None
    assert event.recruiting_project == "2027校园招聘"


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


def test_phone_number_fragment_does_not_break_valid_chinese_datetime() -> None:
    event = parse_record(
        mail(
            "【京东校招】2027 TET 综合面面试通知",
            (
                "紧急事宜请致电400-618-5106（服务时间为工作日9:00-18:00）。"
                "面试方式：视频面试（群面）。"
                "面试时间：2026年08月06日 14点00分，面试时长60分钟。"
            ),
        )
    )
    assert event is not None
    assert event.start_at == datetime(2026, 8, 6, 14, 0, tzinfo=SHANGHAI)
    assert event.end_at == datetime(2026, 8, 6, 15, 0, tzinfo=SHANGHAI)
    assert event.stage == "群面"
    assert event.event_type == "interview"
    assert event.round == "群面"
    assert event.role == "TET 综合方向"
    assert "400-618-5106" not in event.action_summary


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


def test_invitation_and_expiry_are_parsed_as_validity_window(tmp_path) -> None:
    event = parse_record(
        mail(
            "【样例公司】校园招聘在线测评通知",
            (
                "本次测试邀请于2026年07月20日 19:53，"
                "于2026年07月25日 19:53失效。请尽快完成测评。"
            ),
        )
    )
    assert event is not None
    assert event.start_at == datetime(2026, 7, 20, 19, 53, tzinfo=SHANGHAI)
    assert event.end_at == datetime(2026, 7, 25, 19, 53, tzinfo=SHANGHAI)
    assert event.deadline_at is None
    task = task_from_event(event, MarkdownTaskStore(tmp_path))
    assert critical_time(task) == datetime(2026, 7, 25, 19, 53, tzinfo=SHANGHAI)


def test_netease_business_units_share_parent_but_not_application_chain(tmp_path) -> None:
    leihuo = parse_record(
        mail(
            "【网易游戏雷火校招】2027校园招聘在线测评通知",
            "感谢您投递产品经理岗位，请尽快完成在线测评。",
            "<netease-leihuo@example.invalid>",
        )
    )
    interactive = parse_record(
        mail(
            "【网易游戏互娱校招】2027校园招聘在线测评通知",
            "感谢您投递产品经理岗位，请尽快完成在线测评。",
            "<netease-interactive@example.invalid>",
        )
    )
    assert leihuo is not None and interactive is not None
    assert leihuo.company == interactive.company == "网易游戏"
    assert leihuo.recruiting_project == "雷火事业群 · 2027校园招聘"
    assert interactive.recruiting_project == "互娱事业群 · 2027校园招聘"
    assert application_id(leihuo) != application_id(interactive)
    store = MarkdownTaskStore(tmp_path)
    leihuo_task = task_from_event(leihuo, store)
    store.save(leihuo_task)
    interactive_task = task_from_event(interactive, store)
    assert leihuo_task.application_id != interactive_task.application_id


def test_netease_pending_application_is_not_marked_submitted(tmp_path) -> None:
    event = parse_record(
        mail(
            "【网易游戏雷火校招】内推提醒",
            "恭喜你解锁雷火内推特权，待你完成网申后内推才会正式生效！",
            "<netease-pending@example.invalid>",
        )
    )
    assert event is not None
    assert event.company == "网易游戏"
    assert event.recruiting_project == "雷火事业群"
    assert event.stage == "招聘通知"
    assert event.event_type == "notice"
    task = task_from_event(event, MarkdownTaskStore(tmp_path))
    assert task.status == "needs_review"


def test_generic_online_label_falls_back_to_sender_company() -> None:
    record = MailRecord(
        uid="duoyi-online",
        subject="在线测评通知",
        message_id="<duoyi-online@example.invalid>",
        sender="多益网络招聘 <hr@example.invalid>",
        received_at=datetime(2026, 7, 23, 16, 21, tzinfo=SHANGHAI),
        body="感谢应聘 产品策划助理 岗位，已进入在线测评环节。",
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "多益网络"


def test_generic_recruiting_cycle_label_falls_back_to_sender_company() -> None:
    record = MailRecord(
        uid="xpeng-27",
        subject="小鹏集团-【27届校招】项目管理培训生-AI测评邀请",
        message_id="<xpeng-27@example.invalid>",
        sender="小鹏汽车 <hr@example.invalid>",
        received_at=datetime(2026, 7, 13, 9, 9, tzinfo=SHANGHAI),
        body="我们诚挚地邀请您参加【27届校招】项目管理培训生的AI测评面试。",
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "小鹏汽车"
    assert event.recruiting_project == "2027校园招聘"


def test_application_receipt_beats_process_list_offer_noise() -> None:
    record = MailRecord(
        uid="netease-receipt",
        subject="【网易招聘】简历投递成功，请确认职位信息",
        message_id="<netease-receipt@example.invalid>",
        sender="NetEase_HR <hr@example.invalid>",
        received_at=datetime(2026, 8, 1, 23, 23, tzinfo=SHANGHAI),
        body=(
            "【网易游戏雷火校招】您的简历已经收到。"
            "投递项目：2027届雷火秋季校园招聘 职位名称：游戏AI产品经理。"
            "流程为：简历投递 → 简历筛选 → 笔试/测试 → 面试 → 测评 → offer。"
        ),
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "网易游戏"
    assert event.stage == "网申"
    assert event.event_type == "application"
    assert event.recruiting_project == "雷火事业群 · 2027校园招聘"


def test_fanruan_application_receipt_extracts_role_and_ignores_process_round() -> None:
    record = MailRecord(
        uid="fanruan-receipt",
        subject="【帆软招聘】帆软校园招聘简历投递成功通知",
        message_id="<fanruan-receipt@example.invalid>",
        sender="帆软招聘 <hr@example.invalid>",
        received_at=datetime(2026, 8, 3, 16, 7, tzinfo=SHANGHAI),
        body=(
            "帆软2027届秋季校招招聘 提前批。恭喜您网申成功提交。"
            "意向岗位：产品经理\n"
            "招聘流程：网申→简历筛选→笔试→面试→offer。"
        ),
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "帆软"
    assert event.role == "产品经理"
    assert event.recruiting_project == "2027校园招聘 · 提前批"
    assert event.stage == "网申"
    assert event.event_type == "application"
    assert event.round is None


def test_netease_submitted_role_sentence_is_extracted() -> None:
    record = MailRecord(
        uid="netease-interactive-receipt",
        subject="【网易游戏互娱校招】简历投递成功提醒",
        message_id="<netease-interactive-receipt@example.invalid>",
        sender="NetEase_HR <hr@example.invalid>",
        received_at=datetime(2026, 7, 24, 16, 52, tzinfo=SHANGHAI),
        body=(
            "感谢参加网易游戏互娱校园招聘！"
            "您投递的 AI策略运营 职位，简历已成功提交。"
        ),
    )
    event = parse_record(record)
    assert event is not None
    assert event.company == "网易游戏"
    assert event.role == "AI策略运营"
    assert event.recruiting_project == "互娱事业群"
    assert event.event_type == "application"


def test_netease_referral_instruction_is_not_a_role() -> None:
    event = parse_record(
        mail(
            "【网易游戏】雷火事业群校招内推邀请你尽快完成网申！",
            "请确认投递的是雷火事业群校招职位，否则内推状态将无法匹配。",
        )
    )
    assert event is not None
    assert event.role is None


def test_role_parser_rejects_instruction_as_role() -> None:
    event = parse_record(
        mail(
            "【网易游戏】雷火事业群校招内推成功确认邮件",
            "职位：请到官网 campus.163.com/app/personal/apply，前往个人中心应聘记录进行修改。",
        )
    )
    assert event is not None
    assert event.role is None


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


def test_reparsed_existing_notice_becomes_done_when_it_is_a_rejection(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    original = parse_record(
        mail(
            "【小鹏汽车】校园招聘通知",
            "感谢关注校园招聘，后续请留意招聘通知。",
            "<reclassified@example.invalid>",
        )
    )
    assert original is not None
    task = task_from_event(original, store)
    store.save(task)
    corrected = parse_record(
        mail(
            "小鹏汽车校园招聘应聘结果反馈",
            "未来有适合您的职位开放时，我们将第一时间联系您。",
            "<reclassified@example.invalid>",
        )
    )
    assert corrected is not None
    updated = task_from_event(corrected, store)
    assert updated.id == task.id
    assert updated.status == "done"


def test_same_source_replay_restores_original_received_time(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    original_event = parse_record(
        mail(
            "【样例公司】网申成功通知",
            "我们已收到你的申请。",
            "<same-source-time@example.invalid>",
        )
    )
    assert original_event is not None
    task = task_from_event(original_event, store)
    task.received_at = datetime(2026, 8, 3, 18, 0, tzinfo=SHANGHAI)
    store.save(task)

    replayed = task_from_event(original_event, store)
    assert replayed.id == task.id
    assert replayed.received_at == datetime(2026, 7, 29, 12, 0, tzinfo=SHANGHAI)


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


def test_new_source_event_does_not_inherit_completed_state(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    original = parse_record(
        mail(
            "【样例公司】2027校园招聘在线测评通知",
            "请尽快完成在线测评。",
            "<old-assessment@example.invalid>",
        )
    )
    assert original is not None
    old_task = task_from_event(original, store)
    old_task.status = "done"
    old_task.completed_at = datetime(2026, 8, 1, 12, 0, tzinfo=SHANGHAI)
    store.save(old_task)

    new_event = parse_record(
        MailRecord(
            uid="new-assessment",
            subject="【样例公司】2027校园招聘在线测评通知",
            message_id="<new-assessment@example.invalid>",
            sender="招聘团队 <noreply@example.invalid>",
            received_at=datetime(2026, 8, 3, 18, 18, tzinfo=SHANGHAI),
            body="建议您在48小时内完成在线测评。",
        )
    )
    assert new_event is not None
    new_task = task_from_event(new_event, store)
    assert new_task.id != old_task.id
    assert new_task.status == "planned"
    assert new_task.completed_at is None


def test_jd_jds_does_not_attach_to_tet_application(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    tet = parse_record(
        mail(
            "【京东校招】2027 TET 综合面面试通知",
            "面试方式：视频群面。面试时间：2026年08月06日 14:00。",
            "<jd-tet@example.invalid>",
        )
    )
    assert tet is not None
    tet_task = task_from_event(tet, store)
    store.save(tet_task)

    jds = parse_record(
        MailRecord(
            uid="jd-jds",
            subject="【京东校招】2027 JDS测评通知",
            message_id="<jd-jds@example.invalid>",
            sender="京东校招 <hr@example.invalid>",
            received_at=datetime(2026, 8, 3, 18, 18, tzinfo=SHANGHAI),
            body="建议您在48小时内完成在线测评。",
        )
    )
    assert jds is not None
    jds_task = task_from_event(jds, store)
    assert jds_task.application_id != tet_task.application_id
    assert jds_task.role != "TET 综合方向"


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
