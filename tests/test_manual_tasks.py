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
