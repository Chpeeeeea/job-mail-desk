from datetime import datetime

from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.progress import (
    create_progress_template,
    export_progress,
    progress_payload,
    sync_task_to_ledger,
    sync_current_applications_to_ledger,
)


def task(task_id: str, stage: str, status: str, hour: int) -> JobTask:
    return JobTask(
        id=(task_id + "a") * 12,
        application_id="a" * 20,
        company="样例公司",
        role="产品经理",
        recruiting_project="2027 校招",
        event_type="interview",
        stage=stage,
        round="一面" if stage == "面试" else None,
        received_at=datetime(2026, 8, 1, hour, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 8, 6, hour, 0, tzinfo=SHANGHAI),
        end_at=None,
        deadline_at=None,
        priority="high",
        status=status,  # type: ignore[arg-type]
        change_type="new",
        source_message_hash="b" * 32,
        research_status="not_queued",
        confidence=1.0,
        title=stage,
        action_summary=f"处理{stage}",
    )


def test_progress_groups_application_chain_and_preserves_manual_region(tmp_path) -> None:
    written = task("1", "笔试", "done", 10)
    interview = task("2", "面试", "planned", 14)
    applications = progress_payload([written, interview])
    assert len(applications) == 1
    assert applications[0]["current_stage"] == "一面已安排"
    assert applications[0]["application_state"] == "active"
    assert applications[0]["stage_state"] == "scheduled"
    assert [item["stage"] for item in applications[0]["history"]] == [
        "面试",
        "笔试",
    ]

    output = tmp_path / "求职当前进展.md"
    export_progress([written, interview], output)
    content = output.read_text(encoding="utf-8").replace(
        "<!-- 本区可手写复盘或决策；自动刷新不会覆盖。 -->",
        "我的手动判断",
    )
    output.write_text(content, encoding="utf-8")
    export_progress([written, interview], output)
    refreshed = output.read_text(encoding="utf-8")
    assert "样例公司｜产品经理" in refreshed
    assert "> [!abstract]- 样例公司｜产品经理 · 一面已安排" in refreshed
    assert "> | 完成时间 | — |" in refreshed
    assert "> **流程记录**" in refreshed
    assert "面试｜一面｜已安排" in refreshed
    assert "<!-- jobmaildesk:application:aaaaaaaaaaaaaaaaaaaa -->" in refreshed
    assert "- [x] 2026-08-06 10:00｜笔试｜已完成 <!-- jobmaildesk:1a1a1a1a1a1a1a1a1a1a1a1a -->" in refreshed
    assert "- [ ] 2026-08-06 14:00｜面试｜一面｜已安排 <!-- jobmaildesk:2a2a2a2a2a2a2a2a2a2a2a2a -->" in refreshed
    assert "我的手动判断" in refreshed


def test_completed_task_updates_only_exact_ledger_row(tmp_path) -> None:
    completed = task("6", "人才测评", "done", 12)
    completed.company = "科大讯飞"
    completed.role = "AI产品经理"
    completed.application_id = "c" * 20
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """# 岗位投递决策台账

### 已投递或已进入流程

- [ ] 科大讯飞｜AI 产品经理（J13348）｜**已投递**｜保留我的下一步动作
- [x] 科大讯飞｜项目经理（J10000）｜**一面已确认**｜不要修改这一行

### 当前优先待投
""",
        encoding="utf-8",
    )
    assert sync_task_to_ledger(completed, ledger) == 1
    content = ledger.read_text(encoding="utf-8")
    assert "- [x] 科大讯飞｜AI 产品经理（J13348）｜**人才测评已完成，等待后续**｜保留我的下一步动作" in content
    assert "<!-- jobmaildesk:application:cccccccccccccccccccc -->" in content
    assert "项目经理（J10000）｜**一面已确认**｜不要修改这一行" in content


def test_ledger_sync_refuses_ambiguous_role_match(tmp_path) -> None:
    completed = task("7", "笔试", "done", 12)
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**已投递**｜第一条
- [x] 样例公司｜产品经理｜**已投递**｜第二条
### 当前优先待投
""",
        encoding="utf-8",
    )
    assert sync_task_to_ledger(completed, ledger) == 0
    assert "笔试已完成" not in ledger.read_text(encoding="utf-8")


def test_confirmed_application_is_added_to_ledger_once(tmp_path) -> None:
    submitted = task("8", "网申", "confirmed", 12)
    submitted.event_type = "application"
    submitted.start_at = None
    submitted.end_at = None
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程

### 当前优先待投
""",
        encoding="utf-8",
    )
    assert sync_task_to_ledger(submitted, ledger) == 1
    assert sync_task_to_ledger(submitted, ledger) == 0
    content = ledger.read_text(encoding="utf-8")
    assert content.count("jobmaildesk:application:aaaaaaaaaaaaaaaaaaaa") == 1
    assert "- [x] 样例公司｜产品经理｜**2026-08-01 网申已提交，等待简历筛选**" in content


def test_jd_tet_ledger_alias_merges_into_mail_application(tmp_path) -> None:
    interview = task("9", "群面", "planned", 14)
    interview.company = "京东"
    interview.role = "TET 综合方向"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 京东｜TET 管理培训生（综合方向）｜**群面已确认**｜准备案例
### 当前优先待投
""",
        encoding="utf-8",
    )
    applications = progress_payload([interview], ledger)
    assert len(applications) == 1
    assert applications[0]["application_id"] == interview.application_id
    assert applications[0]["ledger_status"] == "群面已确认"


def test_netease_business_unit_ledger_merges_with_parent_company_task(tmp_path) -> None:
    submitted = task("b", "网申", "confirmed", 12)
    submitted.company = "网易游戏"
    submitted.role = "游戏AI产品经理"
    submitted.recruiting_project = "雷火事业群 · 2027校园招聘"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 网易雷火｜游戏 AI 产品经理｜**已完成投递，等待筛选**｜保留复盘
### 当前优先待投
""",
        encoding="utf-8",
    )
    applications = progress_payload([submitted], ledger)
    assert len(applications) == 1
    assert applications[0]["company"] == "网易游戏"
    assert applications[0]["project"] == "雷火事业群 · 2027校园招聘"
    assert applications[0]["ledger_status"] == "已完成投递，等待筛选"


def test_ended_ledger_result_overrides_stale_mail_stage(tmp_path) -> None:
    assessment = task("result", "人才测评", "done", 12)
    assessment.company = "科大讯飞"
    assessment.role = "AI产品经理"
    assessment.application_key = "app-iflytek"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 科大讯飞｜AI 产品经理（J13348）｜**2026-08-05 未通过（简历筛选未通过）**｜简历挂，停止跟进 <!-- jobmaildesk:application:app-iflytek -->
### 当前优先待投
""",
        encoding="utf-8",
    )
    applications = progress_payload([assessment], ledger)
    assert len(applications) == 1
    assert applications[0]["current_stage"] == "2026-08-05 已结束 · 简历筛选未通过"
    assert applications[0]["current_status"] == "done"
    assert applications[0]["status_label"] == "2026-08-05 已结束 · 简历筛选未通过"
    assert applications[0]["application_state"] == "ended"
    assert applications[0]["stage_state"] == "completed"
    assert applications[0]["result"] == "failed"
    assert applications[0]["status_at"] == "2026-08-05"
    assert applications[0]["active"] is False
    assert applications[0]["next_time"] is None
    assert applications[0]["history"][0]["stage"] == "人才测评"


def test_scanner_sync_does_not_reopen_user_ended_application(tmp_path) -> None:
    completed = task("ended-control", "一面", "done", 12)
    completed.application_key = "app-ended-control"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**2026-09-01 已结束 · 一面未通过**｜停止跟进 <!-- jobmaildesk:application:app-ended-control -->
### 当前优先待投
""",
        encoding="utf-8",
    )

    assert sync_task_to_ledger(completed, ledger) == 0
    content = ledger.read_text(encoding="utf-8")
    assert "2026-09-01 已结束 · 一面未通过" in content
    assert "一面已完成，等待后续" not in content


def test_completed_stage_waiting_and_expired_statuses_are_canonical(tmp_path) -> None:
    completed = task("status", "在线笔试", "done", 12)
    completed.completed_at = datetime(2026, 8, 28, 20, 0, tzinfo=SHANGHAI)
    completed.application_key = "app-status"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**2026-08-28 等待后续已完成**｜等待结果 <!-- jobmaildesk:application:app-status -->
### 当前优先待投
""",
        encoding="utf-8",
    )

    application = progress_payload([completed], ledger)[0]
    assert application["current_stage"] == "2026-08-28 在线笔试已完成，等待结果"
    assert application["status_label"] == application["current_stage"]
    assert application["application_state"] == "active"
    assert application["stage_state"] == "completed"
    assert application["result"] == "pending"

    expired = task("expiry", "人才测评", "expired", 13)
    application = progress_payload([expired])[0]
    assert application["current_stage"] == "2026-08-06 人才测评已过期 · 待确认"
    assert application["application_state"] == "expired"
    assert application["stage_state"] == "expired"
    assert application["active"] is False

    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**2026-08-29 群面待确认**｜等待人工确认 <!-- jobmaildesk:application:app-status -->
### 当前优先待投
""",
        encoding="utf-8",
    )
    pending = progress_payload([completed], ledger)[0]
    assert pending["current_stage"] == "2026-08-29 群面待确认"
    assert pending["application_state"] == "pending"
    assert pending["stage_state"] == "waiting"
    assert pending["active"] is False


def test_contradictory_failed_status_is_rendered_as_ended(tmp_path) -> None:
    assessment = task("failed", "人才测评", "done", 12)
    assessment.application_key = "app-failed"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**约2026-08-28 人才测评未通过已完成，等待后续**｜停止跟进 <!-- jobmaildesk:application:app-failed -->
### 当前优先待投
""",
        encoding="utf-8",
    )

    application = progress_payload([assessment], ledger)[0]
    assert application["current_stage"] == "约2026-08-28 已结束 · 人才测评未通过"
    assert application["application_state"] == "ended"
    assert application["result"] == "failed"
    assert application["active"] is False


def test_completed_notice_keeps_application_in_progress_without_generic_done() -> None:
    notice = task("notice", "招聘通知", "done", 12)
    notice.event_type = "notice"
    notice.completed_at = datetime(2026, 8, 22, 12, 59, tzinfo=SHANGHAI)

    application = progress_payload([notice])[0]
    assert application["current_stage"] == "2026-08-22 招聘通知，等待后续"
    assert application["status_label"] == application["current_stage"]
    assert application["application_state"] == "active"
    assert application["stage_state"] == "waiting"
    assert application["result"] == "pending"
    assert application["active"] is True


def test_application_status_contract_is_company_agnostic(tmp_path) -> None:
    """Every application follows the same lifecycle contract, regardless of company."""
    scheduled = task("contract-scheduled", "面试", "planned", 9)
    completed = task("contract-completed", "人才测评", "done", 10)
    notice = task("contract-notice", "招聘通知", "done", 11)
    notice.event_type = "notice"
    notice.completed_at = datetime(2026, 8, 22, 12, 59, tzinfo=SHANGHAI)
    expired = task("contract-expired", "人才测评", "expired", 13)

    terminal = task("contract-terminal", "人才测评", "done", 12)
    terminal.company = "任意公司"
    terminal.role = "任意岗位"
    terminal.application_key = "app-contract-terminal"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 任意公司｜任意岗位｜**2026-08-28 人才测评未通过**｜停止跟进 <!-- jobmaildesk:application:app-contract-terminal -->
### 当前优先待投
""",
        encoding="utf-8",
    )

    cases = [
        (
            progress_payload([scheduled])[0],
            ("active", "scheduled", "pending", "一面已安排"),
        ),
        (
            progress_payload([completed])[0],
            (
                "active",
                "completed",
                "pending",
                "2026-08-06 人才测评已完成，等待结果",
            ),
        ),
        (
            progress_payload([notice])[0],
            ("active", "waiting", "pending", "2026-08-22 招聘通知，等待后续"),
        ),
        (
            progress_payload([terminal], ledger)[0],
            (
                "ended",
                "completed",
                "failed",
                "2026-08-28 已结束 · 人才测评未通过",
            ),
        ),
        (
            progress_payload([expired])[0],
            (
                "expired",
                "expired",
                "pending",
                "2026-08-06 人才测评已过期 · 待确认",
            ),
        ),
    ]

    for application, expected in cases:
        state, stage_state, result, label = expected
        assert application["application_state"] == state
        assert application["stage_state"] == stage_state
        assert application["result"] == result
        assert application["current_stage"] == label
        assert application["status_label"] == label
        assert application["active"] is (state == "active")


def test_user_ledger_fields_override_progress_card_with_stable_id(tmp_path) -> None:
    interview = task("edit", "AI 面试", "planned", 14)
    interview.company = "旧企业名"
    interview.role = "旧岗位名"
    interview.application_key = "app-1234567890abcdef1234"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [ ] OPPO｜AI 产品经理｜**群面已安排**｜准备群面案例 <!-- jobmaildesk:application:app-1234567890abcdef1234 -->
### 当前优先待投
""",
        encoding="utf-8",
    )

    application = progress_payload([interview], ledger)[0]
    assert application["company"] == "OPPO"
    assert application["role"] == "AI 产品经理"
    assert application["current_stage"] == "群面已安排"
    assert application["current_action"] == "准备群面案例"


def test_progress_ignores_instruction_text_when_selecting_role() -> None:
    correct = task("c", "网申", "done", 10)
    correct.company = "网易游戏"
    correct.role = "游戏AI产品经理"
    corrupt = task("d", "招聘通知", "done", 11)
    corrupt.company = "网易游戏"
    corrupt.role = "请到官网 campus.163.com 前往个人中心应聘记录进行修改"
    applications = progress_payload([correct, corrupt])
    assert len(applications) == 1
    assert applications[0]["role"] == "游戏AI产品经理"


def test_batch_ledger_sync_uses_current_application_node(tmp_path) -> None:
    old_assessment = task("e", "AI 面试", "done", 10)
    old_assessment.company = "京东"
    old_assessment.role = "TET 综合方向"
    current_group = task("f", "群面", "planned", 14)
    current_group.company = "京东"
    current_group.role = "TET 综合方向"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 京东｜TET 管理培训生（综合方向）｜**AI 面试已完成**｜准备案例
### 当前优先待投
""",
        encoding="utf-8",
    )
    assert sync_current_applications_to_ledger(
        [current_group, old_assessment], ledger
    ) == 1
    content = ledger.read_text(encoding="utf-8")
    assert "**群面已安排**" in content
    assert "**AI 面试已完成**" not in content


def test_irrelevant_items_do_not_enter_progress() -> None:
    ignored = task("3", "招聘通知", "irrelevant", 9)
    assert progress_payload([ignored]) == []


def test_decision_ledger_adds_companies_without_mail_tasks(tmp_path) -> None:
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """# 岗位投递决策台账

### 已投递或已进入流程

- [x] 样例甲｜产品经理｜**一面邀请**｜准备项目表达
- [x] 样例甲｜项目经理｜**已投递**｜等待后续
- [x] 样例乙｜管培生｜**已结束：未通过**｜保留复盘

### 当前优先待投
""",
        encoding="utf-8",
    )
    applications = progress_payload([], ledger)
    assert [item["company"] for item in applications] == [
        "样例甲",
        "样例甲",
        "样例乙",
    ]
    assert applications[0]["active"] is True
    assert applications[1]["active"] is True
    assert applications[2]["active"] is False


def test_ignored_company_is_not_reintroduced_from_ledger(tmp_path) -> None:
    ignored = task("4", "招聘通知", "irrelevant", 9)
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 样例公司｜产品经理｜**已投递**｜等待后续
### 当前优先待投
""",
        encoding="utf-8",
    )
    assert progress_payload([ignored], ledger) == []


def test_company_alias_is_used_when_suppressing_ignored_ledger_entry(tmp_path) -> None:
    ignored = task("5", "未通过", "irrelevant", 9)
    ignored.company = "deeproute.ai"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 元戎启行｜产品经理｜**已投递**｜等待后续
### 当前优先待投
""",
        encoding="utf-8",
    )
    assert progress_payload([ignored], ledger) == []


def test_progress_template_is_safe_and_never_overwrites(tmp_path) -> None:
    ledger = tmp_path / "求职进展台账.md"
    assert create_progress_template(ledger) is True
    content = ledger.read_text(encoding="utf-8")
    assert "### 已投递或已进入流程" in content
    assert "公司｜岗位｜当前进展｜下一步动作" in content
    assert progress_payload([], ledger) == []
    ledger.write_text(content + "\n我的内容\n", encoding="utf-8")
    assert create_progress_template(ledger) is False
    assert ledger.read_text(encoding="utf-8").endswith("我的内容\n")
