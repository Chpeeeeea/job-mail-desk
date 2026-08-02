from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


APP_NAME = "JobMailDesk"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _local_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", PROJECT_ROOT / "local")) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


LOCAL_ROOT = _local_root()
CONFIG_PATH = LOCAL_ROOT / "config.toml"
TASKS_DIR = LOCAL_ROOT / "tasks"
DIGESTS_DIR = LOCAL_ROOT / "digests"
LOG_DIR = LOCAL_ROOT / "logs"
STATE_DB = LOCAL_ROOT / "state.db"
RESEARCH_QUEUE = LOCAL_ROOT / "research-queue.jsonl"
DASHBOARD_FILE = LOCAL_ROOT / "JobMailDesk.md"
DASHBOARD_CACHE = LOCAL_ROOT / "dashboard-cache.json"
DEFAULT_OBSIDIAN_OUTPUT = LOCAL_ROOT / "求职硬截止待办集.md"
DEFAULT_PROGRESS_OUTPUT = LOCAL_ROOT / "求职当前进展.md"


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
    obsidian_enabled: bool = False
    obsidian_output: Path = DEFAULT_OBSIDIAN_OUTPUT
    include_sender: bool = False
    include_private_links: bool = False
    progress_enabled: bool = False
    progress_output: Path = DEFAULT_PROGRESS_OUTPUT
    progress_source: Path | None = None
    research_enabled: bool = False
    research_queue: Path = RESEARCH_QUEUE
    ui_width: int = 480
    ui_height: int = 740
    always_on_top: bool = True
    start_hidden: bool = False
    updates_enabled: bool = True
    update_channel: str = "preview"


def ensure_directories() -> None:
    for path in (
        LOCAL_ROOT,
        TASKS_DIR,
        DIGESTS_DIR,
        LOG_DIR,
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
enabled = false
output_path = "{output}"
include_sender = false
include_private_links = false

[research]
enabled = false
queue_path = "{queue}"

[progress]
enabled = false
output_path = "{str(DEFAULT_PROGRESS_OUTPUT).replace(chr(92), chr(92) * 2)}"
source_path = ""

[ui]
width = 480
height = 740
always_on_top = true
start_hidden = false

[updates]
enabled = true
channel = "preview"
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
    progress = payload.get("progress", {})
    ui = payload.get("ui", {})
    updates = payload.get("updates", {})
    update_channel = str(updates.get("channel", "preview"))
    if update_channel not in {"stable", "preview"}:
        update_channel = "preview"
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
        progress_enabled=bool(progress.get("enabled", False)),
        progress_output=Path(
            str(progress.get("output_path") or DEFAULT_PROGRESS_OUTPUT)
        ),
        progress_source=(
            Path(str(progress.get("source_path")))
            if progress.get("source_path")
            else None
        ),
        # Legacy versions could persist research.enabled=true. Core no longer
        # creates research queues, so the old switch is intentionally ignored.
        research_enabled=False,
        research_queue=Path(str(research.get("queue_path") or RESEARCH_QUEUE)),
        ui_width=int(ui.get("width", 480)),
        ui_height=int(ui.get("height", 740)),
        always_on_top=bool(ui.get("always_on_top", True)),
        start_hidden=bool(ui.get("start_hidden", False)),
        updates_enabled=bool(updates.get("enabled", True)),
        update_channel=update_channel,
    )


def _toml_string(value: str | Path) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def write_settings(settings: Settings, path: Path = CONFIG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    digests = ", ".join(f'"{item}"' for item in settings.digest_times)
    source = _toml_string(settings.progress_source or "")
    text = f'''[mail]
host = "{_toml_string(settings.mail_host)}"
port = {settings.mail_port}
folder = "{_toml_string(settings.mail_folder)}"
lookback_days = {settings.lookback_days}
poll_minutes = {settings.poll_minutes}

[schedule]
hourly_minute = {settings.hourly_minute}
digest_times = [{digests}]
timezone = "{_toml_string(settings.timezone)}"

[obsidian]
enabled = {str(settings.obsidian_enabled).lower()}
output_path = "{_toml_string(settings.obsidian_output)}"
include_sender = {str(settings.include_sender).lower()}
include_private_links = {str(settings.include_private_links).lower()}

[research]
enabled = {str(settings.research_enabled).lower()}
queue_path = "{_toml_string(settings.research_queue)}"

[progress]
enabled = {str(settings.progress_enabled).lower()}
output_path = "{_toml_string(settings.progress_output)}"
source_path = "{source}"

[ui]
width = {settings.ui_width}
height = {settings.ui_height}
always_on_top = {str(settings.always_on_top).lower()}
start_hidden = {str(settings.start_hidden).lower()}

[updates]
enabled = {str(settings.updates_enabled).lower()}
channel = "{_toml_string(settings.update_channel)}"
'''
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def settings_from_payload(
    current: Settings,
    payload: dict[str, object],
) -> Settings:
    poll_minutes = max(5, min(120, int(payload.get("poll_minutes") or 10)))
    lookback_days = max(1, min(30, int(payload.get("lookback_days") or 3)))
    obsidian_output = Path(
        str(payload.get("obsidian_output") or current.obsidian_output)
    )
    progress_output = Path(
        str(payload.get("progress_output") or current.progress_output)
    )
    progress_source_value = str(payload.get("progress_source") or "").strip()
    update_channel = str(
        payload.get("update_channel") or current.update_channel
    ).strip()
    if update_channel not in {"stable", "preview"}:
        raise ValueError("更新通道必须是 stable 或 preview。")
    return replace(
        current,
        poll_minutes=poll_minutes,
        lookback_days=lookback_days,
        obsidian_enabled=bool(payload.get("obsidian_enabled", False)),
        obsidian_output=obsidian_output,
        progress_enabled=bool(payload.get("progress_enabled", False)),
        progress_output=progress_output,
        progress_source=(Path(progress_source_value) if progress_source_value else None),
        research_enabled=False,
        updates_enabled=bool(payload.get("updates_enabled", current.updates_enabled)),
        update_channel=update_channel,
    )
