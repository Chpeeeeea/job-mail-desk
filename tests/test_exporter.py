from datetime import datetime

from job_mail_desk.config import Settings
from job_mail_desk.exporter import export_dashboard, import_checked_states
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI


def sample_task() -> JobTask:
    return JobTask(
        id="1" * 24,
        application_id="2" * 20,
        company="样例公司",
        role="数据分析",
        recruiting_project=None,
        event_type="interview",
        stage="面试",
        round="一面",
        received_at=datetime(2026, 7, 30, 10, 0, tzinfo=SHANGHAI),
        start_at=None,
        end_at=None,
        deadline_at=None,
        priority="high",
        status="needs_review",
        change_type="new",
        source_message_hash="3" * 32,
        research_status="not_queued",
        confidence=0.7,
        title="面试时间待定",
        action_summary="等待确认面试时间",
    )


def test_manual_region_survives_and_checkbox_syncs_back(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path / "tasks")
    item = sample_task()
    store.save(item)
    output = tmp_path / "todo.md"
    settings = Settings(obsidian_enabled=True, obsidian_output=output)
    export_dashboard(store.all(), output, settings)
    content = output.read_text(encoding="utf-8")
    content = content.replace(
        "<!-- 可在这里添加自己的待办；自动更新不会覆盖本区。 -->",
        "我的手写待办",
    )
    content = content.replace(
        f"- [ ] **时间待确认**｜{item.company}",
        f"- [x] **时间待确认**｜{item.company}",
    )
    output.write_text(content, encoding="utf-8")
    assert import_checked_states(output, store) == 1
    assert store.load(item.id).status == "done"  # type: ignore[union-attr]
    export_dashboard(store.all(), output, settings)
    assert "我的手写待办" in output.read_text(encoding="utf-8")

    content = output.read_text(encoding="utf-8").replace(
        f"- [x] **时间待确认**｜{item.company}",
        f"- [ ] **时间待确认**｜{item.company}",
    )
    output.write_text(content, encoding="utf-8")
    assert import_checked_states(output, store) == 1
    assert store.load(item.id).status == "needs_review"  # type: ignore[union-attr]


def test_irrelevant_tasks_are_not_exported(tmp_path) -> None:
    item = sample_task()
    item.status = "irrelevant"
    output = tmp_path / "todo.md"
    export_dashboard([item], output, Settings(), now=item.received_at)
    assert item.company not in output.read_text(encoding="utf-8")


def test_unchecked_confirmed_task_preserves_progress_status(tmp_path) -> None:
    store = MarkdownTaskStore(tmp_path / "tasks")
    item = sample_task()
    item.status = "confirmed"
    store.save(item)
    output = tmp_path / "todo.md"
    settings = Settings(obsidian_enabled=True, obsidian_output=output)
    export_dashboard(store.all(), output, settings)

    assert import_checked_states(output, store) == 0
    assert store.load(item.id).status == "confirmed"  # type: ignore[union-attr]


def test_expired_task_does_not_enter_todo_export(tmp_path) -> None:
    item = sample_task()
    item.status = "expired"
    output = tmp_path / "todo.md"
    export_dashboard([item], output, Settings(), now=item.received_at)

    content = output.read_text(encoding="utf-8")
    assert item.company not in content
    assert "已过期但未完成" not in content


def test_confirmed_application_without_time_stays_out_of_todo(tmp_path) -> None:
    item = sample_task()
    item.event_type = "application"
    item.stage = "网申"
    item.status = "confirmed"
    output = tmp_path / "todo.md"
    export_dashboard([item], output, Settings(), now=item.received_at)
    assert item.company not in output.read_text(encoding="utf-8")
