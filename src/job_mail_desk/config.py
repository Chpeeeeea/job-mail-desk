from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "JobMailDesk"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT = Path(os.environ.get("LOCALAPPDATA", PROJECT_ROOT / "local")) / APP_NAME
CONFIG_PATH = LOCAL_ROOT / "config.toml"
TASKS_DIR = LOCAL_ROOT / "tasks"
DIGESTS_DIR = LOCAL_ROOT / "digests"
LOG_DIR = LOCAL_ROOT / "logs"
STATE_DB = LOCAL_ROOT / "state.db"
RESEARCH_QUEUE = LOCAL_ROOT / "research-queue.jsonl"
DASHBOARD_FILE = LOCAL_ROOT / "JobMailDesk.md"
PAPERS_DIR = LOCAL_ROOT / "papers"
PAPER_BACKUPS_DIR = LOCAL_ROOT / "paper-backups"
NOTE_ASSETS_DIR = LOCAL_ROOT / "note-assets"
TRASH_DIR = LOCAL_ROOT / "trash"
PREFERENCES_FILE = LOCAL_ROOT / "preferences.json"
WINDOW_STATE_FILE = LOCAL_ROOT / "window-state.json"
DEFAULT_OBSIDIAN_OUTPUT = Path(
    os.environ.get("USERPROFILE", str(LOCAL_ROOT.parent))
) / Path(
    r"iCloudDrive\iCloud~md~obsidian\Mobile\求职硬截止待办集.md"
)


@dataclass(frozen=True)
class Settings:
    mail_host: str = "imap.qq.com"
    mail_port: int = 993
    mail_folder: str = "INBOX"
    lookback_days: int = 3
    poll_minutes: int = 10
    hourly_minute: int = 0
    digest_times: tuple[str, ...] = ("08:00", "13:00", "20:00")
    timezone: str = "Asia/Shanghai"
    obsidian_enabled: bool = True
    obsidian_output: Path = DEFAULT_OBSIDIAN_OUTPUT
    include_sender: bool = False
    include_private_links: bool = False
    research_enabled: bool = True
    research_queue: Path = RESEARCH_QUEUE
    ui_width: int = 390
    ui_height: int = 620
    always_on_top: bool = True
    start_hidden: bool = False


def ensure_directories() -> None:
    for path in (
        LOCAL_ROOT,
        TASKS_DIR,
        DIGESTS_DIR,
        LOG_DIR,
        PAPERS_DIR,
        PAPER_BACKUPS_DIR,
        NOTE_ASSETS_DIR,
        TRASH_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _default_config_text() -> str:
    output = str(DEFAULT_OBSIDIAN_OUTPUT).replace("\\", "\\\\")
    queue = str(RESEARCH_QUEUE).replace("\\", "\\\\")
    return f"""[mail]
host = "imap.qq.com"
port = 993
folder = "INBOX"
lookback_days = 3
poll_minutes = 10

[schedule]
hourly_minute = 0
digest_times = ["08:00", "13:00", "20:00"]
timezone = "Asia/Shanghai"

[obsidian]
enabled = true
output_path = "{output}"
include_sender = false
include_private_links = false

[research]
enabled = true
queue_path = "{queue}"

[ui]
width = 390
height = 620
always_on_top = true
start_hidden = false
"""


def ensure_config() -> Path:
    ensure_directories()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_default_config_text(), encoding="utf-8")
    return CONFIG_PATH


def load_settings(path: Path | None = None) -> Settings:
    config_path = path or ensure_config()
    if not config_path.exists():
        return Settings()
    with config_path.open("rb") as stream:
        payload = tomllib.load(stream)
    mail = payload.get("mail", {})
    schedule = payload.get("schedule", {})
    obsidian = payload.get("obsidian", {})
    research = payload.get("research", {})
    ui = payload.get("ui", {})
    return Settings(
        mail_host=str(mail.get("host", "imap.qq.com")),
        mail_port=int(mail.get("port", 993)),
        mail_folder=str(mail.get("folder", "INBOX")),
        lookback_days=int(mail.get("lookback_days", 3)),
        poll_minutes=max(1, int(mail.get("poll_minutes", 10))),
        hourly_minute=int(schedule.get("hourly_minute", 0)),
        digest_times=tuple(schedule.get("digest_times", ["08:00", "13:00", "20:00"])),
        timezone=str(schedule.get("timezone", "Asia/Shanghai")),
        obsidian_enabled=bool(obsidian.get("enabled", False)),
        obsidian_output=Path(
            str(obsidian.get("output_path") or DEFAULT_OBSIDIAN_OUTPUT)
        ),
        include_sender=bool(obsidian.get("include_sender", False)),
        include_private_links=bool(obsidian.get("include_private_links", False)),
        research_enabled=bool(research.get("enabled", True)),
        research_queue=Path(str(research.get("queue_path") or RESEARCH_QUEUE)),
        ui_width=int(ui.get("width", 390)),
        ui_height=int(ui.get("height", 620)),
        always_on_top=bool(ui.get("always_on_top", True)),
        start_hidden=bool(ui.get("start_hidden", False)),
    )
