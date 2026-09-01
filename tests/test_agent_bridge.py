from datetime import datetime

import pytest

from job_mail_desk.agent_bridge import apply_task_update, list_tasks
from job_mail_desk.config import Settings
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI


def sample_task() -> JobTask:
    return JobTask(
        id="a" * 24,
        application_id="b" * 20,
        company="京东",
        role="TET 综合方向",
        recruiting_project="2027校园招聘",
        event_type="manual",
        stage="群面",
        round="群面",
        received_at=datetime(2026, 8, 1, 10, 0, tzinfo=SHANGHAI),
        start_at=datetime(2026, 8, 6, 14, 0, tzinfo=SHANGHAI),
        end_at=None,
        deadline_at=None,
        priority="high",
        status="planned",
        change_type="new",
        source_message_hash="manual",
        research_status="not_queued",
        confidence=1.0,
        title="京东群面",
        action_summary="参加京东群面",
    )


def test_agent_update_syncs_obsidian_and_can_restore(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path / "tasks")
    task = sample_task()
    store.save(task)
    obsidian = tmp_path / "obsidian.md"
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 京东｜TET 综合方向｜**群面已确认**｜保留准备计划
### 当前优先待投
""",
        encoding="utf-8",
    )
    settings = Settings(
        obsidian_enabled=True,
        obsidian_output=obsidian,
        progress_enabled=True,
        progress_output=tmp_path / "求职当前进展.md",
        progress_source=ledger,
    )

    completed = apply_task_update(
        settings,
        task.id,
        {"status": "done", "manual_notes": "用户在对话中确认完成"},
        store=store,
        local_dashboard=tmp_path / "dashboard.md",
    )
    assert completed["task"]["status"] == "done"
    saved = store.load(task.id)
    assert saved is not None
    assert saved.manual_notes == "用户在对话中确认完成"
    assert saved.change_type == "update"
    assert saved.completed_at is not None
    assert saved.start_at == datetime(2026, 8, 6, 14, 0, tzinfo=SHANGHAI)
    assert f"jobmaildesk:{task.id}" in obsidian.read_text(encoding="utf-8")
    assert "- [x]" in obsidian.read_text(encoding="utf-8")
    assert "群面已完成，等待后续" in ledger.read_text(encoding="utf-8")
    assert "- [x] 京东｜TET 综合方向" in ledger.read_text(encoding="utf-8")
    assert f"jobmaildesk:application:{task.application_id}" in ledger.read_text(
        encoding="utf-8"
    )
    progress = settings.progress_output.read_text(encoding="utf-8")
    assert f"jobmaildesk:application:{task.application_id}" in progress
    assert f"jobmaildesk:{task.id}" in progress

    restored = apply_task_update(
        settings,
        task.id,
        {"status": "planned"},
        store=store,
        local_dashboard=tmp_path / "dashboard.md",
    )
    assert restored["task"]["status"] == "planned"
    restored_task = store.load(task.id)
    assert restored_task is not None
    assert restored_task.completed_at is None
    assert "- [ ]" in obsidian.read_text(encoding="utf-8")
    assert "- [ ] 京东｜TET 综合方向" in ledger.read_text(encoding="utf-8")


def test_agent_list_filters_and_update_requires_exact_id(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path / "tasks")
    task = sample_task()
    store.save(task)
    matches = list_tasks(company="京东", stage="群面", store=store)
    assert [item["id"] for item in matches] == [task.id]
    with pytest.raises(KeyError):
        apply_task_update(
            Settings(),
            "f" * 24,
            {"status": "done"},
            store=store,
            local_dashboard=tmp_path / "dashboard.md",
        )


def test_edit_application_status_ends_chain_without_rewriting_task(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path / "tasks")
    task = sample_task()
    store.save(task)
    ledger = tmp_path / "岗位投递决策台账.md"
    ledger.write_text(
        """### 已投递或已进入流程
- [x] 京东｜TET 综合方向｜**群面已完成，等待后续**｜保留面试历史 <!-- jobmaildesk:application:bbbbbbbbbbbbbbbbbbbb -->
### 当前优先待投
""",
        encoding="utf-8",
    )
    settings = Settings(
        progress_enabled=True,
        progress_output=tmp_path / "求职当前进展.md",
        progress_source=ledger,
    )

    apply_task_update(
        settings,
        task.id,
        {"application_state": "ended", "application_result": "群面未通过"},
        store=store,
        local_dashboard=tmp_path / "dashboard.md",
    )

    saved = store.load(task.id)
    assert saved is not None
    assert saved.status == "planned"
    assert saved.stage == "群面"
    assert "已结束 · 群面未通过" in ledger.read_text(encoding="utf-8")
    assert "保留面试历史" in ledger.read_text(encoding="utf-8")
    assert "已结束 · 群面未通过" in settings.progress_output.read_text(
        encoding="utf-8"
    )
