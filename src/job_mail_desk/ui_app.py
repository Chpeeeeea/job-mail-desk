from __future__ import annotations

import os
import ctypes
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


def _enable_high_dpi_rendering() -> None:
    """Prevent Windows from bitmap-scaling the whole WebView on HiDPI screens."""
    if sys.platform != "win32":
        return
    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        set_context(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


_enable_high_dpi_rendering()

import webview
from apscheduler.schedulers.base import SchedulerNotRunningError
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from .config import (
    CONFIG_PATH,
    DASHBOARD_FILE,
    STATE_DB,
    TASKS_DIR,
    Settings,
    settings_from_payload,
    write_settings,
)
from .agent_bridge import apply_task_update, sync_outputs
from .credentials import MailCredential, load_credential, save_credential
from .mail_reader import ImapReader
from .dashboard import cached_dashboard_payload
from .markdown_store import MarkdownTaskStore
from .research import request_states
from .progress import create_progress_template
from .scanner import scan_once
from .scheduler import create_background_scheduler
from .state import StateStore
from .task_service import create_manual_task


def _resource(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return root / "job_mail_desk" / "ui" / name if hasattr(sys, "_MEIPASS") else Path(__file__).parent / "ui" / name


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


def _open_obsidian_uri(path: Path) -> None:
    webbrowser.open(
        f"obsidian://open?vault={quote(path.parent.name)}&file={quote(path.stem)}"
    )


CAPSULE_WIDTH = 36
CAPSULE_HEIGHT = 88
CAPSULE_VISIBLE_EDGE = 32
EDITOR_WIDTH = 680
EDITOR_HEIGHT = 820
INSTANCE_MUTEX_NAME = r"Local\JobMailDesk.Desktop.Singleton.v1"
ERROR_ALREADY_EXISTS = 183


def _window_handle(window: Any) -> int:
    handle = window.native.Handle
    return int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(handle)


def _hide_from_task_switcher(window: Any) -> None:
    """Keep the tray-managed widget out of the taskbar and Alt+Tab."""
    if sys.platform != "win32" or os.environ.get("JOBMAILDESK_UI_QA") == "1":
        return
    hwnd = _window_handle(window)
    user32 = ctypes.windll.user32
    get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    extended_style = get_style(hwnd, -20)
    extended_style = (extended_style | 0x00000080) & ~0x00040000
    set_style(hwnd, -20, extended_style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0037)


def show_existing_window(
    title: str = "JobMailDesk",
    *,
    wait_seconds: float = 0,
) -> bool:
    """Reveal the existing tray-managed window without launching a duplicate."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            user32.SetForegroundWindow(hwnd)
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _claim_single_instance(
    name: str = INSTANCE_MUTEX_NAME,
) -> tuple[Any | None, bool]:
    """Atomically claim the desktop instance before any window is created."""
    if sys.platform == "darwin":
        import fcntl

        lock_path = CONFIG_PATH.parent / "instance.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None, False
        return handle, True
    if sys.platform != "win32":
        return None, True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    handle = create_mutex(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    already_exists = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    if already_exists:
        kernel32.CloseHandle(handle)
        return None, False
    return int(handle), True


def _close_instance_handle(handle: Any | None) -> None:
    if sys.platform == "win32" and handle:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
    elif sys.platform == "darwin" and handle:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _capsule_anchor(
    x: int,
    y: int,
    width: int = CAPSULE_WIDTH,
    height: int = CAPSULE_HEIGHT,
) -> tuple[int, int, int]:
    """Calculate a movable, multi-monitor edge anchor for a capsule."""
    screens = list(webview.screens)
    if not screens:
        return x, x, y
    center_x = x + width // 2
    center_y = y + height // 2

    def distance(screen: Any) -> int:
        nearest_x = min(max(center_x, screen.x), screen.x + screen.width)
        nearest_y = min(max(center_y, screen.y), screen.y + screen.height)
        return (center_x - nearest_x) ** 2 + (center_y - nearest_y) ** 2

    screen = min(screens, key=distance)
    left_distance = abs(x - screen.x)
    right_distance = abs(screen.x + screen.width - (x + width))
    on_left = left_distance <= right_distance
    shown_x = screen.x + 2 if on_left else screen.x + screen.width - width - 2
    hidden_x = (
        screen.x - width + CAPSULE_VISIBLE_EDGE
        if on_left
        else screen.x + screen.width - CAPSULE_VISIBLE_EDGE
    )
    target_y = max(
        screen.y + 28,
        min(y, screen.y + screen.height - height - 40),
    )
    return hidden_x, shown_x, target_y


class DesktopApi:
    def __init__(
        self,
        settings: Settings,
        on_settings_saved: Callable[[Settings], None] | None = None,
    ) -> None:
        self._settings = settings
        self._on_settings_saved = on_settings_saved
        self._window: Any = None
        self._scan_lock = threading.Lock()
        self._expanded_geometry: tuple[int, int, int, int] | None = None
        self._capsule_positions: tuple[int, int, int] | None = None
        self._capsule_snap_timer: threading.Timer | None = None
        self._editor_geometry: tuple[int, int, int, int] | None = None
        self._dashboard_lock = threading.Lock()

    def get_dashboard(self) -> dict[str, object]:
        with self._dashboard_lock:
            return cached_dashboard_payload(
                self._settings.research_queue,
                self._settings.progress_source,
            )

    def get_app_settings(self) -> dict[str, object]:
        try:
            credential = load_credential()
            credential_configured = True
            email = credential.email
        except RuntimeError:
            credential_configured = False
            email = ""
        return {
            "credential_configured": credential_configured,
            "email": email,
            "mail_host": self._settings.mail_host,
            "poll_minutes": self._settings.poll_minutes,
            "lookback_days": self._settings.lookback_days,
            "obsidian_enabled": self._settings.obsidian_enabled,
            "obsidian_output": str(self._settings.obsidian_output),
            "progress_enabled": self._settings.progress_enabled,
            "progress_output": str(self._settings.progress_output),
            "progress_source": str(self._settings.progress_source or ""),
            "config_path": str(CONFIG_PATH),
            "research_enabled": self._settings.research_enabled,
        }

    def save_app_settings(self, payload: dict[str, object]) -> dict[str, object]:
        authorization_code = str(payload.get("authorization_code") or "").strip()
        try:
            load_credential()
            credential_configured = True
        except RuntimeError:
            credential_configured = False
        if authorization_code:
            save_credential(str(payload.get("email") or ""), authorization_code)
            credential_configured = True
        if not credential_configured:
            raise ValueError("首次使用必须填写QQ邮箱和IMAP授权码。")

        updated = settings_from_payload(self._settings, payload)
        for label, enabled, path in (
            ("Obsidian输出", updated.obsidian_enabled, updated.obsidian_output),
            ("求职进展输出", updated.progress_enabled, updated.progress_output),
        ):
            if enabled and path.suffix.lower() != ".md":
                raise ValueError(f"{label}必须是 .md 文件。")
        if updated.progress_source and updated.progress_source.suffix.lower() != ".md":
            raise ValueError("手动进展台账必须是 .md 文件。")
        if updated.obsidian_enabled:
            updated.obsidian_output.parent.mkdir(parents=True, exist_ok=True)
        if updated.progress_enabled:
            updated.progress_output.parent.mkdir(parents=True, exist_ok=True)
        write_settings(updated)
        self._settings = updated
        self._export(MarkdownTaskStore(TASKS_DIR))
        if self._on_settings_saved:
            self._on_settings_saved(updated)
        return self.get_app_settings()

    def test_mail_settings(self, payload: dict[str, object]) -> dict[str, object]:
        email = str(payload.get("email") or "").strip()
        authorization_code = str(payload.get("authorization_code") or "").strip()
        if not authorization_code:
            try:
                existing = load_credential()
            except RuntimeError:
                return {"ok": False, "detail": "请先填写IMAP授权码。"}
            email = email or existing.email
            authorization_code = existing.authorization_code
        try:
            temporary_settings = settings_from_payload(self._settings, payload)
            snapshot = ImapReader(
                temporary_settings,
                MailCredential(email=email, authorization_code=authorization_code),
            ).mailbox_snapshot()
            return {
                "ok": True,
                "detail": f"只读连接成功，当前未读 {snapshot['unseen']} 封。",
            }
        except Exception as exc:
            return {"ok": False, "detail": f"连接失败：{exc}"}

    def select_markdown_path(self, kind: str) -> str:
        if not self._window:
            return ""
        defaults = {
            "obsidian_output": self._settings.obsidian_output,
            "progress_output": self._settings.progress_output,
            "progress_source": self._settings.progress_source
            or self._settings.progress_output.with_name("求职进展台账.md"),
        }
        if kind not in defaults:
            raise ValueError("不支持的路径类型")
        default = defaults[kind]
        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(default.parent),
            save_filename=default.name,
            file_types=("Markdown (*.md)",),
        )
        return str(selected[0]) if selected else ""

    def create_progress_source_template(self, path_value: str) -> dict[str, object]:
        path = Path(path_value.strip())
        if not path_value.strip() or path.suffix.lower() != ".md":
            raise ValueError("请选择一个 .md 进展台账路径。")
        created = create_progress_template(path)
        return {"created": created, "path": str(path)}

    def update_status(self, task_id: str, status: str) -> dict[str, object]:
        store = MarkdownTaskStore(TASKS_DIR)
        apply_task_update(self._settings, task_id, {"status": status}, store=store)
        return self.get_dashboard()

    def snooze(self, task_id: str, until: str) -> dict[str, object]:
        snoozed = datetime.fromisoformat(until)
        store = MarkdownTaskStore(TASKS_DIR)
        task = store.load(task_id)
        if not task:
            raise KeyError(task_id)
        store.update_status(task_id, "planned", snoozed_until=snoozed)
        self._export(store)
        return self.get_dashboard()

    def trigger_scan(self) -> dict[str, object]:
        if not self._scan_lock.acquire(blocking=False):
            return {"status": "busy"}
        try:
            return {"status": "ok", "summary": scan_once(self._settings).to_dict()}
        finally:
            self._scan_lock.release()

    def open_source(self, task_id: str) -> bool:
        task = MarkdownTaskStore(TASKS_DIR).load(task_id)
        if not task or not task.source_url:
            return False
        webbrowser.open(task.source_url)
        return True

    def open_obsidian(self, task_id: str) -> bool:
        if self._settings.obsidian_enabled and self._settings.obsidian_output.exists():
            _open_obsidian_uri(self._settings.obsidian_output)
            return True
        task_path = MarkdownTaskStore(TASKS_DIR).path_for(task_id)
        if task_path.exists():
            _open_path(task_path)
            return True
        return False

    def open_research(self, task_id: str) -> bool:
        payload = request_states(self._settings.research_queue).get(task_id, {})
        result_path = Path(str(payload.get("result_path") or ""))
        if result_path.is_file():
            _open_path(result_path)
            return True
        return False

    def get_health(self) -> dict[str, str | None]:
        return StateStore(STATE_DB).health()

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        store = MarkdownTaskStore(TASKS_DIR)
        create_manual_task(payload, store)
        self._export(store)
        return self.get_dashboard()

    def edit_task(
        self,
        task_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        store = MarkdownTaskStore(TASKS_DIR)
        apply_task_update(self._settings, task_id, payload, store=store)
        return self.get_dashboard()

    def set_capsule(self, compact: bool) -> bool:
        if not self._window:
            return False
        threading.Thread(
            target=self._apply_capsule_geometry,
            args=(compact,),
            daemon=True,
        ).start()
        return True

    def set_editor_mode(self, enabled: bool) -> bool:
        if not self._window:
            return False
        threading.Thread(
            target=self._apply_editor_geometry,
            args=(enabled,),
            daemon=True,
        ).start()
        return True

    def _apply_editor_geometry(self, enabled: bool) -> None:
        if not self._window:
            return
        if enabled:
            if self._editor_geometry is None:
                self._editor_geometry = (
                    self._window.x,
                    self._window.y,
                    self._window.width,
                    self._window.height,
                )
            old_x, old_y, old_width, old_height = self._editor_geometry
            width = max(EDITOR_WIDTH, old_width)
            height = max(EDITOR_HEIGHT, old_height)
            screens = list(webview.screens)
            target_x = old_x - (width - old_width) // 2
            target_y = old_y - (height - old_height) // 2
            if screens:
                center_x = old_x + old_width // 2
                center_y = old_y + old_height // 2
                screen = next(
                    (
                        item
                        for item in screens
                        if item.x <= center_x < item.x + item.width
                        and item.y <= center_y < item.y + item.height
                    ),
                    screens[0],
                )
                width = min(width, screen.width - 32)
                height = min(height, screen.height - 56)
                target_x = max(
                    screen.x + 16,
                    min(target_x, screen.x + screen.width - width - 16),
                )
                target_y = max(
                    screen.y + 28,
                    min(target_y, screen.y + screen.height - height - 28),
                )
            self._window.resize(width, height)
            self._window.move(target_x, target_y)
        elif self._editor_geometry is not None:
            x, y, width, height = self._editor_geometry
            self._editor_geometry = None
            self._window.resize(width, height)
            self._window.move(x, y)

    def _apply_capsule_geometry(self, compact: bool) -> None:
        if not self._window:
            return
        if compact:
            self._expanded_geometry = (
                self._window.x,
                self._window.y,
                self._window.width,
                self._window.height,
            )
            capsule_width, capsule_height = CAPSULE_WIDTH, CAPSULE_HEIGHT
            self._window.resize(capsule_width, capsule_height)
            self._capsule_positions = _capsule_anchor(
                self._window.x,
                self._window.y,
            )
            hidden_x, _, target_y = self._capsule_positions
            self._window.move(hidden_x, target_y)
        else:
            if self._capsule_snap_timer:
                self._capsule_snap_timer.cancel()
                self._capsule_snap_timer = None
            self._capsule_positions = None
            if self._expanded_geometry:
                x, y, width, height = self._expanded_geometry
                self._window.resize(width, height)
                self._window.move(x, y)
            else:
                self._window.resize(self._settings.ui_width, self._settings.ui_height)

    def on_window_moved(self, x: int, y: int) -> None:
        if self._capsule_positions:
            self._capsule_positions = _capsule_anchor(x, y)
            hidden_x, _, target_y = self._capsule_positions
            if abs(x - hidden_x) <= 1 and abs(y - target_y) <= 1:
                return
            if self._capsule_snap_timer:
                self._capsule_snap_timer.cancel()
            self._capsule_snap_timer = threading.Timer(
                0.25,
                self._snap_capsule_after_drag,
            )
            self._capsule_snap_timer.daemon = True
            self._capsule_snap_timer.start()

    def _snap_capsule_after_drag(self) -> None:
        if not self._window or not self._capsule_positions:
            return
        hidden_x, _, target_y = self._capsule_positions
        self._window.move(hidden_x, target_y)

    def _export(self, store: MarkdownTaskStore) -> None:
        sync_outputs(self._settings, store)


def _tray_image() -> Image.Image:
    custom_icon = Path(sys.executable).resolve().parent / "JobMailDesk.ico"
    if custom_icon.exists():
        try:
            return Image.open(custom_icon).convert("RGBA").resize((64, 64))
        except OSError:
            pass
    image = Image.new("RGBA", (64, 64), "#f6f0e6")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 7, 56, 57), radius=10, fill="#25231f")
    draw.rectangle((18, 19, 46, 23), fill="#e85d3f")
    draw.rectangle((18, 30, 42, 34), fill="#f6f0e6")
    draw.rectangle((18, 41, 37, 45), fill="#f6f0e6")
    return image



def _run_ui_primary(settings: Settings) -> None:
    scheduler_holder: dict[str, Any] = {"value": None}
    scheduler_lock = threading.Lock()

    def stop_scheduler() -> None:
        with scheduler_lock:
            current = scheduler_holder["value"]
            scheduler_holder["value"] = None
        if not current:
            return
        try:
            current.shutdown(wait=False)
        except SchedulerNotRunningError:
            pass

    def apply_runtime_settings(updated: Settings) -> None:
        stop_scheduler()
        scheduler = create_background_scheduler(updated)
        scheduler.start()
        with scheduler_lock:
            scheduler_holder["value"] = scheduler

    api = DesktopApi(settings, on_settings_saved=apply_runtime_settings)
    try:
        load_credential()
    except RuntimeError:
        pass
    else:
        apply_runtime_settings(settings)
    window = webview.create_window(
        "JobMailDesk",
        _resource("index.html").as_uri(),
        js_api=api,
        width=settings.ui_width,
        height=settings.ui_height,
        frameless=True,
        on_top=settings.always_on_top,
        background_color="#f6f0e6",
        easy_drag=False,
        min_size=(36, 82),
        hidden=settings.start_hidden,
    )
    api._window = window
    window.events.moved += api.on_window_moved
    window.events.before_show += lambda: _hide_from_task_switcher(window)
    paused = {"value": False}

    def show() -> None:
        window.show()

    def hide() -> None:
        window.hide()

    def scan() -> None:
        threading.Thread(target=api.trigger_scan, daemon=True).start()

    def toggle_pause() -> None:
        scheduler = scheduler_holder["value"]
        if not scheduler:
            return
        paused["value"] = not paused["value"]
        for job_id in ("mail-poll", "hourly-refresh"):
            if paused["value"]:
                scheduler.pause_job(job_id)
            else:
                scheduler.resume_job(job_id)

    def open_obsidian() -> None:
        target = (
            api._settings.obsidian_output
            if api._settings.obsidian_enabled
            else DASHBOARD_FILE
        )
        if target.exists():
            if api._settings.obsidian_enabled:
                _open_obsidian_uri(target)
            else:
                _open_path(target)

    def open_settings() -> None:
        window.show()
        window.evaluate_js(
            "setCapsule(false).then(() => "
            "window.openSettingsDialog && window.openSettingsDialog(false))"
        )

    def quit_app(icon: Icon, _item: MenuItem | None = None) -> None:
        stop_scheduler()
        icon.stop()
        window.destroy()

    tray: Icon | None = None
    if sys.platform == "win32":
        tray = Icon(
            "JobMailDesk",
            _tray_image(),
            "JobMailDesk",
            Menu(
                MenuItem("显示", lambda _icon, _item: show(), default=True),
                MenuItem("隐藏", lambda _icon, _item: hide()),
                MenuItem("立即扫描", lambda _icon, _item: scan()),
                MenuItem(
                    lambda _item: "恢复扫描" if paused["value"] else "暂停扫描",
                    lambda _icon, _item: toggle_pause(),
                    checked=lambda _item: paused["value"],
                ),
                MenuItem("设置", lambda _icon, _item: open_settings()),
                MenuItem("打开 Obsidian", lambda _icon, _item: open_obsidian()),
                MenuItem("退出", quit_app),
            ),
        )
        threading.Thread(target=tray.run, daemon=True).start()

    try:
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
        webview.start(debug=False, private_mode=False)
    finally:
        stop_scheduler()
        if tray:
            tray.stop()


def run_ui(settings: Settings) -> None:
    instance_handle, is_primary = _claim_single_instance()
    if not is_primary:
        show_existing_window(wait_seconds=5)
        return
    try:
        _run_ui_primary(settings)
    finally:
        _close_instance_handle(instance_handle)
