from datetime import datetime

from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.progress import (
    create_progress_template,
    export_progress,
    progress_payload,
)


def task(task_id: str, stage: str, status: str, hour: int) -> JobTask:
    return JobTask(
        id=task_id * 24,
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
    assert applications[0]["current_stage"] == "面试"
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
    assert "面试｜一面｜已安排" in refreshed
    assert "我的手动判断" in refreshed


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
