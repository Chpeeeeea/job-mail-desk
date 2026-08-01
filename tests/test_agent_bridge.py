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
    settings = Settings(obsidian_enabled=True, obsidian_output=obsidian)

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
    assert f"jobmaildesk:{task.id}" in obsidian.read_text(encoding="utf-8")
    assert "- [x]" in obsidian.read_text(encoding="utf-8")

    restored = apply_task_update(
        settings,
        task.id,
        {"status": "planned"},
        store=store,
        local_dashboard=tmp_path / "dashboard.md",
    )
    assert restored["task"]["status"] == "planned"
    assert "- [ ]" in obsidian.read_text(encoding="utf-8")


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
