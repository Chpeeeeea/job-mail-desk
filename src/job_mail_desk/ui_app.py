from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import webview
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from .config import (
    DASHBOARD_FILE,
    NOTE_ASSETS_DIR,
    PAPER_BACKUPS_DIR,
    PAPERS_DIR,
    PREFERENCES_FILE,
    STATE_DB,
    TASKS_DIR,
    TRASH_DIR,
    Settings,
)
from .dashboard import dashboard_payload
from .exporter import export_dashboard
from .markdown_store import MarkdownTaskStore
from .image_store import NoteImageStore
from .paper_store import PaperStore
from .preferences import load_preferences, update_preferences
from .research import close_requests_for_task
from .scanner import scan_once
from .scheduler import create_background_scheduler
from .state import StateStore
from .task_service import create_manual_task, edit_task_fields


def _resource(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return root / "job_mail_desk" / "ui" / name if hasattr(sys, "_MEIPASS") else Path(__file__).parent / "ui" / name


def _paper_url(paper_id: str) -> str:
    return f"{_resource('paper.html').as_uri()}#paper={paper_id}"


def _open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


def _open_obsidian_uri(path: Path) -> None:
    webbrowser.open(
        f"obsidian://open?vault={quote(path.parent.name)}&file={quote(path.stem)}"
    )


def _spawn_paper_process(paper_id: str) -> subprocess.Popen[bytes]:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "paper", paper_id]
    else:
        command = [sys.executable, "-m", "job_mail_desk", "paper", paper_id]
    creationflags = (
        subprocess.CREATE_NO_WINDOW
        if sys.platform == "win32"
        else 0
    )
    return subprocess.Popen(command, creationflags=creationflags)


class DesktopApi:
    def __init__(
        self,
        settings: Settings,
        paper_manager: "PaperWindowManager | None" = None,
    ) -> None:
        self.settings = settings
        self.paper_manager = paper_manager
        self.window: Any = None
        self._scan_lock = threading.Lock()
        self._expanded_geometry: tuple[int, int, int, int] | None = None
        self._capsule_positions: tuple[int, int, int] | None = None

    def get_dashboard(self) -> dict[str, object]:
        return dashboard_payload()

    def update_status(self, task_id: str, status: str) -> dict[str, object]:
        if status not in {
            "needs_review",
            "confirmed",
            "planned",
            "done",
            "cancelled",
            "irrelevant",
        }:
            raise ValueError("不支持的任务状态")
        store = MarkdownTaskStore(TASKS_DIR)
        task = store.update_status(task_id, status)
        if status in {"done", "cancelled", "irrelevant"}:
            close_requests_for_task(
                self.settings.research_queue,
                task_id,
                reason=f"task_status:{status}",
            )
            task.research_status = "closed"
            store.save(task)
        self._export(store)
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
            return {"status": "ok", "summary": scan_once(self.settings).to_dict()}
        finally:
            self._scan_lock.release()

    def open_source(self, task_id: str) -> bool:
        task = MarkdownTaskStore(TASKS_DIR).load(task_id)
        if not task or not task.source_url:
            return False
        webbrowser.open(task.source_url)
        return True

    def open_obsidian(self, task_id: str) -> bool:
        if self.settings.obsidian_enabled and self.settings.obsidian_output.exists():
            _open_obsidian_uri(self.settings.obsidian_output)
            return True
        task_path = MarkdownTaskStore(TASKS_DIR).path_for(task_id)
        if task_path.exists():
            _open_path(task_path)
            return True
        return False

    def get_health(self) -> dict[str, str | None]:
        return StateStore(STATE_DB).health()

    def create_task(self, payload: dict[str, object]) -> dict[str, object]:
        store = MarkdownTaskStore(TASKS_DIR)
        create_manual_task(payload, store)
        self._export(store)
        return self.get_dashboard()

    def create_paper(self, kind: str) -> dict[str, object]:
        if not self.paper_manager:
            raise RuntimeError("纸片管理器尚未初始化")
        paper = self.paper_manager.create(kind)
        return paper.to_dict()

    def list_papers(self) -> list[dict[str, object]]:
        if not self.paper_manager:
            return []
        return [paper.metadata() for paper in self.paper_manager.store.all()]

    def get_paper(self, paper_id: str) -> dict[str, object]:
        return PaperApi(self._require_paper_manager(), paper_id).get_paper()

    def save_paper(
        self,
        paper_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return PaperApi(self._require_paper_manager(), paper_id).save_paper(payload)

    def open_paper(self, paper_id: str) -> bool:
        self._require_paper_manager().open(paper_id)
        return True

    def close_paper(self, paper_id: str) -> bool:
        self._require_paper_manager().close(paper_id)
        return True

    def move_paper_to_trash(self, paper_id: str) -> bool:
        self._require_paper_manager().trash(paper_id)
        return True

    def set_paper_capsule(self, paper_id: str, compact: bool) -> bool:
        manager = self._require_paper_manager()
        threading.Thread(
            target=manager.set_capsule,
            args=(paper_id, compact),
            daemon=True,
        ).start()
        return True

    def peek_paper_capsule(self, paper_id: str, reveal: bool) -> bool:
        manager = self._require_paper_manager()
        threading.Thread(
            target=manager.peek_capsule,
            args=(paper_id, reveal),
            daemon=True,
        ).start()
        return True

    def open_paper_external(self, paper_id: str) -> bool:
        path = self._require_paper_manager().store.path_for(paper_id)
        if not path.exists():
            return False
        _open_path(path)
        return True

    def save_note_image(self, data_url: str) -> str:
        return self._require_paper_manager().images.save_data_url(data_url)

    def get_note_image(self, reference: str) -> str | None:
        return self._require_paper_manager().images.data_url(reference)

    def get_preferences(self) -> dict[str, object]:
        return load_preferences(PREFERENCES_FILE).to_dict()

    def save_preferences(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return update_preferences(PREFERENCES_FILE, payload).to_dict()

    def edit_task(
        self,
        task_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        store = MarkdownTaskStore(TASKS_DIR)
        edit_task_fields(task_id, payload, store)
        self._export(store)
        return self.get_dashboard()

    def set_capsule(self, compact: bool) -> bool:
        if not self.window:
            return False
        threading.Thread(
            target=self._apply_capsule_geometry,
            args=(compact,),
            daemon=True,
        ).start()
        return True

    def _apply_capsule_geometry(self, compact: bool) -> None:
        if not self.window:
            return
        if compact:
            self._expanded_geometry = (
                self.window.x,
                self.window.y,
                self.window.width,
                self.window.height,
            )
            capsule_width, capsule_height = 40, 112
            self.window.resize(capsule_width, capsule_height)
            screens = list(webview.screens)
            if screens:
                center_x = self.window.x + capsule_width // 2
                center_y = self.window.y + capsule_height // 2
                screen = next(
                    (
                        candidate
                        for candidate in screens
                        if candidate.x <= center_x < candidate.x + candidate.width
                        and candidate.y <= center_y < candidate.y + candidate.height
                    ),
                    min(
                        screens,
                        key=lambda candidate: abs(
                            center_x - (candidate.x + candidate.width // 2)
                        ),
                    ),
                )
                left_distance = abs(self.window.x - screen.x)
                right_distance = abs(
                    screen.x + screen.width - (self.window.x + capsule_width)
                )
                on_left = left_distance <= right_distance
                shown_x = (
                    screen.x + 2
                    if on_left
                    else screen.x + screen.width - capsule_width - 2
                )
                hidden_x = (
                    screen.x - capsule_width + 13
                    if on_left
                    else screen.x + screen.width - 13
                )
                target_y = max(
                    screen.y + 36,
                    min(
                        self.window.y,
                        screen.y + screen.height - capsule_height - 48,
                    ),
                )
                self._capsule_positions = (hidden_x, shown_x, target_y)
                self.window.move(hidden_x, target_y)
        else:
            self._capsule_positions = None
            if self._expanded_geometry:
                x, y, width, height = self._expanded_geometry
                self.window.resize(width, height)
                self.window.move(x, y)
            else:
                self.window.resize(self.settings.ui_width, self.settings.ui_height)

    def peek_capsule(self, reveal: bool) -> bool:
        if not self.window or not self._capsule_positions:
            return False
        def move() -> None:
            if not self.window or not self._capsule_positions:
                return
            hidden_x, shown_x, y = self._capsule_positions
            self.window.move(shown_x if reveal else hidden_x, y)

        threading.Thread(target=move, daemon=True).start()
        return True

    def _export(self, store: MarkdownTaskStore) -> None:
        tasks = store.all()
        export_dashboard(tasks, DASHBOARD_FILE, self.settings)
        if self.settings.obsidian_enabled:
            export_dashboard(tasks, self.settings.obsidian_output, self.settings)

    def _require_paper_manager(self) -> "PaperWindowManager":
        if not self.paper_manager:
            raise RuntimeError("纸片管理器尚未初始化")
        return self.paper_manager


class PaperApi:
    def __init__(self, manager: "PaperWindowManager", paper_id: str) -> None:
        self.manager = manager
        self.paper_id = paper_id

    def get_paper(self) -> dict[str, object]:
        paper = self.manager.store.load(self.paper_id)
        if not paper:
            raise KeyError(self.paper_id)
        payload = paper.to_dict()
        payload["preferences"] = load_preferences(PREFERENCES_FILE).to_dict()
        payload["notes"] = [
            item.metadata()
            for item in self.manager.store.all()
            if item.kind == "note" and item.id != self.paper_id
        ]
        return payload

    def save_paper(self, payload: dict[str, object]) -> dict[str, object]:
        paper = self.manager.store.update(
            self.paper_id,
            body=str(payload.get("body") or ""),
            title=str(payload.get("title") or "未命名纸片"),
            theme=str(payload.get("theme") or "warm"),
            linked_task_ids=list(payload.get("linked_task_ids") or []),
        )
        window = self.manager.windows.get(self.paper_id)
        if window:
            window.set_title(f"{paper.title} · JobMailDesk")
        return paper.to_dict()

    def create_paper(self, kind: str) -> dict[str, object]:
        return self.manager.create(kind).to_dict()

    def open_paper(self, paper_id: str) -> bool:
        self.manager.open(paper_id)
        return True

    def close_paper(self) -> bool:
        self.manager.close(self.paper_id)
        return True

    def move_to_trash(self) -> bool:
        self.manager.trash(self.paper_id)
        return True

    def set_capsule(self, compact: bool) -> bool:
        threading.Thread(
            target=self.manager.set_capsule,
            args=(self.paper_id, compact),
            daemon=True,
        ).start()
        return True

    def peek_capsule(self, reveal: bool) -> bool:
        threading.Thread(
            target=self.manager.peek_capsule,
            args=(self.paper_id, reveal),
            daemon=True,
        ).start()
        return True

    def open_external(self) -> bool:
        path = self.manager.store.path_for(self.paper_id)
        if not path.exists():
            return False
        _open_path(path)
        return True

    def save_image(self, data_url: str) -> str:
        return self.manager.images.save_data_url(data_url)

    def get_image(self, reference: str) -> str | None:
        return self.manager.images.data_url(reference)

    def get_preferences(self) -> dict[str, object]:
        return load_preferences(PREFERENCES_FILE).to_dict()

    def save_preferences(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return update_preferences(PREFERENCES_FILE, payload).to_dict()


class StandalonePaperApi:
    def __init__(self, settings: Settings, paper_id: str) -> None:
        self.settings = settings
        self.paper_id = paper_id
        self.store = PaperStore(PAPERS_DIR, PAPER_BACKUPS_DIR, TRASH_DIR)
        self.images = NoteImageStore(NOTE_ASSETS_DIR)
        self.window: Any = None
        self.expanded_geometry: tuple[int, int, int, int] | None = None
        self.capsule_positions: tuple[int, int, int] | None = None

    def _check_id(self, paper_id: str) -> None:
        if paper_id != self.paper_id:
            raise PermissionError("纸片窗口只能访问自己的 Markdown")

    def get_paper(self, paper_id: str) -> dict[str, object]:
        self._check_id(paper_id)
        paper = self.store.load(paper_id)
        if not paper:
            raise KeyError(paper_id)
        payload = paper.to_dict()
        payload["preferences"] = load_preferences(PREFERENCES_FILE).to_dict()
        payload["notes"] = [
            item.metadata()
            for item in self.store.all()
            if item.kind == "note" and item.id != paper_id
        ]
        return payload

    def save_paper(
        self,
        paper_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        self._check_id(paper_id)
        paper = self.store.update(
            paper_id,
            body=str(payload.get("body") or ""),
            title=str(payload.get("title") or "未命名纸片"),
            theme=str(payload.get("theme") or "warm"),
            linked_task_ids=list(payload.get("linked_task_ids") or []),
        )
        if self.window:
            self.window.set_title(f"{paper.title} · JobMailDesk")
        return paper.to_dict()

    def create_paper(self, kind: str) -> dict[str, object]:
        if kind not in {"todo", "note"}:
            raise ValueError("纸片类型必须是 todo 或 note")
        paper = self.store.create(
            kind,  # type: ignore[arg-type]
            theme=load_preferences(PREFERENCES_FILE).theme,
        )
        _spawn_paper_process(paper.id)
        return paper.to_dict()

    def open_paper(self, paper_id: str) -> bool:
        if not self.store.load(paper_id):
            return False
        _spawn_paper_process(paper_id)
        return True

    def close_paper(self, paper_id: str) -> bool:
        self._check_id(paper_id)
        if self.window:
            threading.Thread(target=self.window.destroy, daemon=True).start()
        return True

    def move_paper_to_trash(self, paper_id: str) -> bool:
        self._check_id(paper_id)
        self.store.move_to_trash(paper_id)
        if self.window:
            threading.Thread(target=self.window.destroy, daemon=True).start()
        return True

    def set_paper_capsule(self, paper_id: str, compact: bool) -> bool:
        self._check_id(paper_id)
        threading.Thread(
            target=self._apply_capsule,
            args=(compact,),
            daemon=True,
        ).start()
        return True

    def _apply_capsule(self, compact: bool) -> None:
        if not self.window:
            return
        if compact:
            self.expanded_geometry = (
                self.window.x,
                self.window.y,
                self.window.width,
                self.window.height,
            )
            width, height = 40, 112
            self.window.resize(width, height)
            if not load_preferences(PREFERENCES_FILE).auto_snap_capsules:
                return
            screens = list(webview.screens)
            if not screens:
                return
            center_x = self.window.x + width // 2
            center_y = self.window.y + height // 2
            screen = next(
                (
                    candidate
                    for candidate in screens
                    if candidate.x <= center_x < candidate.x + candidate.width
                    and candidate.y <= center_y < candidate.y + candidate.height
                ),
                screens[0],
            )
            left = abs(self.window.x - screen.x) <= abs(
                screen.x + screen.width - (self.window.x + width)
            )
            shown_x = screen.x + 2 if left else screen.x + screen.width - width - 2
            hidden_x = screen.x - width + 13 if left else screen.x + screen.width - 13
            y = max(
                screen.y + 42,
                min(self.window.y, screen.y + screen.height - height - 48),
            )
            self.capsule_positions = (hidden_x, shown_x, y)
            self.window.move(hidden_x, y)
        else:
            self.capsule_positions = None
            if self.expanded_geometry:
                x, y, width, height = self.expanded_geometry
                self.window.resize(width, height)
                self.window.move(x, y)
            else:
                self.window.resize(360, 500)

    def peek_paper_capsule(self, paper_id: str, reveal: bool) -> bool:
        self._check_id(paper_id)
        if not self.window or not self.capsule_positions:
            return False

        def move() -> None:
            if not self.window or not self.capsule_positions:
                return
            hidden_x, shown_x, y = self.capsule_positions
            self.window.move(shown_x if reveal else hidden_x, y)

        threading.Thread(target=move, daemon=True).start()
        return True

    def open_paper_external(self, paper_id: str) -> bool:
        self._check_id(paper_id)
        path = self.store.path_for(paper_id)
        if not path.exists():
            return False
        _open_path(path)
        return True

    def save_note_image(self, data_url: str) -> str:
        return self.images.save_data_url(data_url)

    def get_note_image(self, reference: str) -> str | None:
        return self.images.data_url(reference)

    def get_preferences(self) -> dict[str, object]:
        return load_preferences(PREFERENCES_FILE).to_dict()

    def save_preferences(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return update_preferences(PREFERENCES_FILE, payload).to_dict()


class PaperWindowManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = PaperStore(PAPERS_DIR, PAPER_BACKUPS_DIR, TRASH_DIR)
        self.images = NoteImageStore(NOTE_ASSETS_DIR)
        self.windows: dict[str, Any] = {}
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.expanded_geometry: dict[str, tuple[int, int, int, int]] = {}
        self.compact: set[str] = set()
        self.capsule_positions: dict[str, tuple[int, int, int]] = {}
        self.desktop_api: DesktopApi | None = None

    def create(self, kind: str):
        if kind not in {"todo", "note"}:
            raise ValueError("纸片类型必须是 todo 或 note")
        preferences = load_preferences(PREFERENCES_FILE)
        paper = self.store.create(
            kind,  # type: ignore[arg-type]
            theme=preferences.theme,
        )
        self.open(paper.id)
        return paper

    def open(self, paper_id: str) -> Any:
        existing = self.processes.get(paper_id)
        if existing and existing.poll() is None:
            return existing
        paper = self.store.load(paper_id)
        if not paper:
            raise KeyError(paper_id)
        process = _spawn_paper_process(paper_id)
        self.processes[paper_id] = process
        return process

    def close(self, paper_id: str) -> None:
        process = self.processes.pop(paper_id, None)
        if process and process.poll() is None:
            process.terminate()

    def trash(self, paper_id: str) -> None:
        self.store.move_to_trash(paper_id)
        self.close(paper_id)

    def close_all(self) -> None:
        for paper_id in list(self.processes):
            self.close(paper_id)

    def set_capsule(self, paper_id: str, compact: bool) -> None:
        window = self.windows.get(paper_id)
        if not window:
            return
        if compact:
            self.expanded_geometry[paper_id] = (
                window.x,
                window.y,
                window.width,
                window.height,
            )
            window.resize(40, 112)
            self.compact.add(paper_id)
            self._snap_capsules(paper_id, window)
        else:
            self.compact.discard(paper_id)
            self.capsule_positions.pop(paper_id, None)
            geometry = self.expanded_geometry.get(paper_id)
            if geometry:
                x, y, width, height = geometry
                window.resize(width, height)
                window.move(x, y)
            else:
                window.resize(360, 500)

    def peek_capsule(self, paper_id: str, reveal: bool) -> None:
        window = self.windows.get(paper_id)
        positions = self.capsule_positions.get(paper_id)
        if not window or not positions:
            return
        hidden_x, shown_x, y = positions
        window.move(shown_x if reveal else hidden_x, y)

    def _snap_capsules(self, paper_id: str, active_window: Any) -> None:
        if not load_preferences(PREFERENCES_FILE).auto_snap_capsules:
            return
        screens = list(webview.screens)
        if not screens:
            return
        center_x = active_window.x + active_window.width // 2
        center_y = active_window.y + active_window.height // 2
        screen = next(
            (
                candidate
                for candidate in screens
                if candidate.x <= center_x < candidate.x + candidate.width
                and candidate.y <= center_y < candidate.y + candidate.height
            ),
            screens[0],
        )
        left = abs(active_window.x - screen.x) <= abs(
            screen.x + screen.width - (active_window.x + active_window.width)
        )
        same_side = [
            (paper_id, window)
            for paper_id, window in self.windows.items()
            if paper_id in self.compact and window is not active_window
        ]
        queue_index = len(same_side)
        shown_x = screen.x + 2 if left else screen.x + screen.width - 42
        hidden_x = screen.x - 27 if left else screen.x + screen.width - 13
        y = min(
            screen.y + screen.height - 148,
            max(screen.y + 42, active_window.y) + queue_index * 120,
        )
        self.capsule_positions[paper_id] = (hidden_x, shown_x, y)
        active_window.move(hidden_x, y)


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


def run_paper_ui(settings: Settings, paper_id: str) -> None:
    store = PaperStore(PAPERS_DIR, PAPER_BACKUPS_DIR, TRASH_DIR)
    paper = store.load(paper_id)
    if not paper:
        raise KeyError(paper_id)
    api = StandalonePaperApi(settings, paper_id)
    window = webview.create_window(
        f"{paper.title} · JobMailDesk",
        _paper_url(paper_id),
        js_api=api,
        width=360,
        height=500,
        min_size=(40, 86),
        frameless=True,
        easy_drag=False,
        on_top=True,
        background_color="#f4efe5",
    )
    api.window = window
    webview.start(debug=False, private_mode=False)


def run_ui(settings: Settings, initial_paper: str | None = None) -> None:
    paper_manager = PaperWindowManager(settings)
    api = DesktopApi(settings, paper_manager)
    paper_manager.desktop_api = api
    scheduler = create_background_scheduler(settings)
    scheduler.start()
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
        min_size=(42, 100),
        hidden=settings.start_hidden,
    )
    api.window = window
    paused = {"value": False}

    def show() -> None:
        window.show()

    def hide() -> None:
        window.hide()

    def scan() -> None:
        threading.Thread(target=api.trigger_scan, daemon=True).start()

    def toggle_pause() -> None:
        paused["value"] = not paused["value"]
        for job_id in ("mail-poll", "hourly-refresh"):
            if paused["value"]:
                scheduler.pause_job(job_id)
            else:
                scheduler.resume_job(job_id)

    def open_obsidian() -> None:
        target = settings.obsidian_output if settings.obsidian_enabled else DASHBOARD_FILE
        if target.exists():
            if settings.obsidian_enabled:
                _open_obsidian_uri(target)
            else:
                _open_path(target)

    def new_paper(kind: str) -> None:
        paper_manager.create(kind)

    def quit_app(icon: Icon, _item: MenuItem | None = None) -> None:
        scheduler.shutdown(wait=False)
        paper_manager.close_all()
        icon.stop()
        window.destroy()

    tray = Icon(
        "JobMailDesk",
        _tray_image(),
        "JobMailDesk",
        Menu(
            MenuItem("显示", lambda _icon, _item: show(), default=True),
            MenuItem("隐藏", lambda _icon, _item: hide()),
            MenuItem("立即扫描", lambda _icon, _item: scan()),
            MenuItem("新建待办纸", lambda _icon, _item: new_paper("todo")),
            MenuItem("新建笔记纸", lambda _icon, _item: new_paper("note")),
            MenuItem(
                lambda _item: "恢复扫描" if paused["value"] else "暂停扫描",
                lambda _icon, _item: toggle_pause(),
                checked=lambda _item: paused["value"],
            ),
            MenuItem("打开 Obsidian", lambda _icon, _item: open_obsidian()),
            MenuItem("退出", quit_app),
        ),
    )
    threading.Thread(target=tray.run, daemon=True).start()

    def restore_papers() -> None:
        for paper in paper_manager.store.all():
            paper_manager.open(paper.id)
        if initial_paper in {"todo", "note"}:
            paper_manager.create(initial_paper)

    try:
        webview.start(restore_papers, debug=False, private_mode=False)
    finally:
        scheduler.shutdown(wait=False)
        paper_manager.close_all()
        tray.stop()
