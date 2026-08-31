from datetime import datetime

from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.task_service import create_manual_task, edit_task_fields


def test_create_and_edit_manual_markdown_task(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    task = create_manual_task(
        {
            "company": "个人计划",
            "role": "产品经理",
            "stage": "模拟面试",
            "start_at": "2026-08-05T19:00:00+08:00",
            "end_at": "2026-08-05T20:00:00+08:00",
            "action_summary": "准备产品案例",
            "manual_notes": "先复盘项目，再模拟回答。",
        },
        store,
        now=datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI),
    )
    assert task.status == "planned"
    assert store.path_for(task.id).exists()
    edited = edit_task_fields(
        task.id,
        {
            "start_at": "2026-08-06T20:00:00+08:00",
            "end_at": "2026-08-06T21:00:00+08:00",
            "manual_notes": "已更新准备材料。",
        },
        store,
    )
    assert edited.start_at == datetime(2026, 8, 6, 20, 0, tzinfo=SHANGHAI)
    assert "已更新" in edited.manual_notes


def test_adding_time_promotes_review_task_to_planned(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    task = create_manual_task(
        {
            "company": "样例集团",
            "role": "AI 产品经理",
            "stage": "人才测评",
            "action_summary": "完成人才测评",
        },
        store,
    )
    assert task.status == "needs_review"

    edited = edit_task_fields(
        task.id,
        {
            "start_at": "2026-08-31T14:18:00+08:00",
            "end_at": "2026-09-02T14:18:00+08:00",
        },
        store,
    )

    assert edited.status == "planned"


def test_clearing_all_times_returns_planned_task_to_review(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    task = create_manual_task(
        {
            "company": "样例集团",
            "role": "AI 产品经理",
            "stage": "人才测评",
            "deadline_at": "2026-09-02T14:18:00+08:00",
            "action_summary": "完成人才测评",
        },
        store,
    )
    assert task.status == "planned"

    edited = edit_task_fields(task.id, {"deadline_at": ""}, store)

    assert edited.status == "needs_review"


def test_same_manual_event_updates_instead_of_creating_duplicate(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path)
    payload = {
        "company": "京东",
        "role": "TET 综合方向",
        "stage": "群面",
        "start_at": "2026-08-06T14:00:00+08:00",
        "end_at": "2026-08-06T17:00:00+08:00",
        "action_summary": "参加群面",
    }
    first = create_manual_task(payload, store)
    store.update_status(first.id, "done")
    payload["action_summary"] = "参加群面并提前准备案例"
    second = create_manual_task(payload, store)
    assert second.id == first.id
    assert second.status == "planned"
    assert second.change_type == "update"
    assert len(store.all()) == 1
    assert "提前准备" in second.action_summary
