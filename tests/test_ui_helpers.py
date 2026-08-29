from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from job_mail_desk.config import Settings
from job_mail_desk.markdown_store import MarkdownTaskStore
from job_mail_desk.models import JobTask
from job_mail_desk.parser import SHANGHAI
from job_mail_desk.ui_app import (
    DesktopApi,
    _claim_single_instance,
    _close_instance_handle,
    _open_obsidian_uri,
    show_existing_window,
)


def test_obsidian_button_uses_obsidian_uri(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(
        "job_mail_desk.ui_app.webbrowser.open",
        lambda value: opened.append(value),
    )
    _open_obsidian_uri(Path("D:/Vault/Mobile/求职硬截止待办集.md"))
    assert opened
    assert opened[0].startswith("obsidian://open?")
    assert "vault=Mobile" in opened[0]
    assert ".md" not in opened[0]


def test_editor_mode_expands_and_restores_window(monkeypatch) -> None:
    class Window:
        x = 100
        y = 80
        width = 480
        height = 740

        def resize(self, width, height):
            self.width = width
            self.height = height

        def move(self, x, y):
            self.x = x
            self.y = y

    monkeypatch.setattr(
        "job_mail_desk.ui_app.webview.screens",
        [SimpleNamespace(x=0, y=0, width=1920, height=1080)],
    )
    api = DesktopApi(Settings())
    assert not hasattr(api, "window")
    api._window = Window()
    api._apply_editor_geometry(True)
    assert (api._window.width, api._window.height) == (680, 820)
    api._apply_editor_geometry(False)
    assert (api._window.x, api._window.y, api._window.width, api._window.height) == (
        100,
        80,
        480,
        740,
    )


def test_status_action_updates_obsidian_checkbox_immediately(tmp_path, monkeypatch) -> None:
    task = JobTask(
        id="a" * 24,
        application_id="b" * 20,
        company="京东",
        role="TET 综合方向",
        recruiting_project=None,
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
    tasks_dir = tmp_path / "tasks"
    store = MarkdownTaskStore(tasks_dir)
    store.save(task)
    obsidian = tmp_path / "求职待办.md"
    monkeypatch.setattr("job_mail_desk.ui_app.TASKS_DIR", tasks_dir)
    monkeypatch.setattr("job_mail_desk.ui_app.DASHBOARD_FILE", tmp_path / "local.md")
    api = DesktopApi(Settings(obsidian_enabled=True, obsidian_output=obsidian))

    api.update_status(task.id, "done")
    assert f"- [x] **2026-08-06 14:00**" in obsidian.read_text(encoding="utf-8")
    api.update_status(task.id, "planned")
    assert f"- [ ] **2026-08-06 14:00**" in obsidian.read_text(encoding="utf-8")


def test_desktop_bridge_has_no_public_native_window() -> None:
    api = DesktopApi(Settings())
    assert not hasattr(api, "window")
    assert not hasattr(api, "settings")
    assert not hasattr(api, "download_update")
    assert not hasattr(api, "install_update")


def test_mail_connection_test_uses_unsaved_imap_form_values(monkeypatch) -> None:
    captured = {}

    class Reader:
        def __init__(self, settings, credential):
            captured["settings"] = settings
            captured["credential"] = credential

        def mailbox_snapshot(self):
            return {"unseen": 0, "uidvalidity": "1", "uidnext": "2"}

    monkeypatch.setattr("job_mail_desk.ui_app.ImapReader", Reader)
    monkeypatch.setattr(
        "job_mail_desk.ui_app.load_credential",
        lambda: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    result = DesktopApi(Settings()).test_mail_settings(
        {
            "email": "user@example.test",
            "authorization_code": "one-time-code",
            "mail_provider": "custom",
            "mail_host": "mx.example.test",
            "mail_port": 587,
            "mail_ssl": False,
            "poll_minutes": 10,
            "lookback_days": 3,
            "update_channel": "preview",
        }
    )

    assert result["ok"] is True
    assert captured["settings"].mail_host == "mx.example.test"
    assert captured["settings"].mail_port == 587
    assert captured["settings"].mail_ssl is False
    assert captured["credential"].authorization_code == "one-time-code"


def test_card_actions_use_guarded_clicks_and_no_confirm_state() -> None:
    project_root = Path(__file__).resolve().parents[1]
    html = (project_root / "src/job_mail_desk/ui/index.html").read_text(
        encoding="utf-8"
    )
    javascript = (project_root / "src/job_mail_desk/ui/app.js").read_text(
        encoding="utf-8"
    )
    stylesheet = (project_root / "src/job_mail_desk/ui/style.css").read_text(
        encoding="utf-8"
    )
    assert 'data-action="confirm"' not in html
    assert 'data-action="edit_time"' in html
    assert '>邮件链接<' in html
    assert 'id="settingsDialog"' in html
    assert 'name="mail_provider"' in html
    assert 'value="custom"' in html
    assert 'name="mail_host"' in html
    assert 'name="mail_port"' in html
    assert 'name="mail_ssl"' in html
    assert "邮箱账号" in html
    assert "客户端授权码" in html
    assert "QQ邮箱" not in html
    assert 'id="createProgressTemplate"' in html
    assert 'id="checkUpdates"' in html
    assert 'id="openUpdateRelease"' in html
    assert 'id="selectDictionaryWorkbook"' in html
    assert 'id="compileDictionaryWorkbook"' in html
    assert 'name="dictionary_sheet"' in html
    assert 'id="openUpdateRelease" class="secondary-wide"' in html
    assert '>打开下载页</button>' in html
    assert ".update-actions button" in stylesheet
    assert "font-size: 10px" in stylesheet
    assert 'id="updateBanner"' in html
    assert 'window.openSettingsDialog = showSettingsDialog' in javascript
    assert "applyMailProviderPreset" in javascript
    assert "mail_ssl" in javascript
    assert 'window.checkForUpdates = checkForUpdates' in javascript
    settings_function = javascript.split(
        "async function showSettingsDialog", 1
    )[1].split("window.openSettingsDialog", 1)[0]
    assert "set_editor_mode(true)" not in settings_function
    assert "get_dictionary_status" in javascript
    assert "compile_dictionary_workbook" in javascript
    assert 'new Set(["toggle_done", "snooze", "ignore"])' in javascript
    assert 'button.textContent = "再点确认"' in javascript
    assert 'document.createElement("details")' in javascript
    assert 'toggleAll.textContent = allExpanded ? "收起全部" : "展开全部"' in javascript
    assert '<small>${items.length} 条申请链</small>' in javascript
    assert 'labels.push(`${counts.active} 进行中`)' in javascript
    assert 'labels.push(`${counts.expired} 待确认`)' in javascript
    assert 'labels.push(`${counts.ended} 已结束`)' in javascript
    assert '条申请链 · ${escapeHtml(stages.join' not in javascript
    assert '["active", "进行中"]' in javascript
    assert '["expired", "待确认"]' in javascript
    assert '["ended", "已结束"]' in javascript
    assert 'applicationState(application) === state.progressFilter' in javascript
    assert 'overviewText.textContent = `${allCompanies.size} 家企业 · ${allApplications.length} 条申请链`' in javascript
    assert ".progress-company-state.attention" in stylesheet
    assert "grid-template-columns: 12px minmax(0, 1fr) max-content" in stylesheet


def test_dictionary_status_uses_bundled_defaults(tmp_path, monkeypatch) -> None:
    imported = tmp_path / "dictionaries" / "imported"
    monkeypatch.setattr("job_mail_desk.ui_app.TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(
        "job_mail_desk.ui_app.DICTIONARIES_DIR",
        tmp_path / "dictionaries",
    )
    monkeypatch.setattr(
        "job_mail_desk.ui_app.IMPORTED_DICTIONARIES_DIR",
        imported,
    )
    status = DesktopApi(Settings()).get_dictionary_status()
    assert status["counts"] == {
        "companies": 520,
        "programs": 129,
        "roles": 2825,
        "mail_templates": 4,
    }
    assert status["user_dictionary_enabled"] is False


def test_show_existing_window_is_windows_only(monkeypatch) -> None:
    monkeypatch.setattr("job_mail_desk.ui_app.sys.platform", "linux")
    assert show_existing_window() is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex")
def test_single_instance_mutex_is_atomic() -> None:
    name = rf"Local\JobMailDesk.Test.{uuid4().hex}"
    first_handle, first_primary = _claim_single_instance(name)
    try:
        second_handle, second_primary = _claim_single_instance(name)
        assert first_primary is True
        assert first_handle
        assert second_primary is False
        assert second_handle is None
    finally:
        _close_instance_handle(first_handle)

    replacement_handle, replacement_primary = _claim_single_instance(name)
    try:
        assert replacement_primary is True
        assert replacement_handle
    finally:
        _close_instance_handle(replacement_handle)
