from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from . import __version__
from .parser import PARSER_VERSION


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
APPLICATIONS_DIR = LOCAL_ROOT / "applications"
DICTIONARIES_DIR = LOCAL_ROOT / "dictionaries"
IMPORTED_DICTIONARIES_DIR = DICTIONARIES_DIR / "imported"
MANUAL_DICTIONARIES_DIR = DICTIONARIES_DIR / "manual"
UNRESOLVED_DIR = LOCAL_ROOT / "unresolved"
DIGESTS_DIR = LOCAL_ROOT / "digests"
LOG_DIR = LOCAL_ROOT / "logs"
STATE_DIR = LOCAL_ROOT / "state"
RUNTIME_KIND = "frozen" if getattr(sys, "frozen", False) else "source"
STATE_NAMESPACE = f"{RUNTIME_KIND}-v{__version__}-p{PARSER_VERSION}"
STATE_DB = STATE_DIR / f"state-{STATE_NAMESPACE}.db"
RESEARCH_QUEUE = LOCAL_ROOT / "research-queue.jsonl"
DASHBOARD_FILE = LOCAL_ROOT / "JobMailDesk.md"
DASHBOARD_CACHE = LOCAL_ROOT / "dashboard-cache.json"
DEFAULT_OBSIDIAN_OUTPUT = LOCAL_ROOT / "求职硬截止待办集.md"
DEFAULT_PROGRESS_OUTPUT = LOCAL_ROOT / "求职当前进展.md"


@dataclass(frozen=True)
class MailProviderPreset:
    """Editable defaults for the built-in IMAP provider choices."""

    key: str
    label: str
    host: str
    port: int = 993
    ssl: bool = True


MAIL_PROVIDER_PRESETS: dict[str, MailProviderPreset] = {
    "qq": MailProviderPreset("qq", "QQ", "imap.qq.com"),
    "163": MailProviderPreset("163", "163", "imap.163.com"),
    "126": MailProviderPreset("126", "126", "imap.126.com"),
    "yeah": MailProviderPreset("yeah", "Yeah", "imap.yeah.net"),
    "gmail": MailProviderPreset("gmail", "Gmail", "imap.gmail.com"),
    "outlook": MailProviderPreset("outlook", "Outlook", "outlook.office365.com"),
    "custom": MailProviderPreset("custom", "Custom", ""),
}

# Keep the descriptive alias available to callers that prefer the full name.
EMAIL_PROVIDER_PRESETS = MAIL_PROVIDER_PRESETS
MAIL_PROVIDERS = MAIL_PROVIDER_PRESETS

_MAIL_PROVIDER_ALIASES = {
    "qq邮箱": "qq",
    "qqmail": "qq",
    "网易163": "163",
    "netease163": "163",
    "网易126": "126",
    "netease126": "126",
    "outlook.com": "outlook",
    "office365": "outlook",
    "office 365": "outlook",
}
_MAIL_HOST_PROVIDER = {
    preset.host.casefold(): key
    for key, preset in MAIL_PROVIDER_PRESETS.items()
    if key != "custom" and preset.host
}
# Outlook has had both hostnames in common use. Recognize the older one when
# loading a config while using the current Office 365 hostname for new presets.
_MAIL_HOST_PROVIDER["imap-mail.outlook.com"] = "outlook"


def normalize_mail_provider(value: object) -> str:
    """Return a supported provider key, falling back to ``custom``."""

    candidate = str(value or "").strip().casefold()
    candidate = _MAIL_PROVIDER_ALIASES.get(candidate, candidate)
    return candidate if candidate in MAIL_PROVIDER_PRESETS else "custom"


def infer_mail_provider(host: str | None) -> str:
    """Infer a built-in provider from an IMAP hostname when possible."""

    return _MAIL_HOST_PROVIDER.get(str(host or "").strip().casefold(), "custom")


def mail_provider_preset(provider: object) -> MailProviderPreset:
    """Return the preset for a key, using Custom for unknown values."""

    return MAIL_PROVIDER_PRESETS[normalize_mail_provider(provider)]


def _coerce_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
    return bool(value)


def _coerce_mail_port(
    value: object,
    fallback: int = 993,
    *,
    strict: bool = False,
) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        if strict:
            raise ValueError("IMAP端口必须是 1 到 65535 之间的整数。") from None
        port = fallback
    if not 1 <= port <= 65535:
        raise ValueError("IMAP端口必须在 1 到 65535 之间。")
    return port


@dataclass(frozen=True)
class Settings:
    mail_provider: str = "qq"
    mail_host: str = "imap.qq.com"
    mail_port: int = 993
    mail_ssl: bool = True
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

    @property
    def provider(self) -> str:
        """Compatibility alias for callers using the shorter field name."""

        return self.mail_provider

    @property
    def ssl(self) -> bool:
        """Compatibility alias for the persisted IMAP SSL setting."""

        return self.mail_ssl

    @property
    def use_ssl(self) -> bool:
        return self.mail_ssl


def ensure_directories() -> None:
    for path in (
        LOCAL_ROOT,
        TASKS_DIR,
        APPLICATIONS_DIR,
        DICTIONARIES_DIR,
        IMPORTED_DICTIONARIES_DIR,
        MANUAL_DICTIONARIES_DIR,
        UNRESOLVED_DIR,
        DIGESTS_DIR,
        LOG_DIR,
        STATE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _default_config_text() -> str:
    output = str(DEFAULT_OBSIDIAN_OUTPUT).replace("\\", "\\\\")
    queue = str(RESEARCH_QUEUE).replace("\\", "\\\\")
    return f"""[mail]
provider = "qq"
host = "imap.qq.com"
port = 993
ssl = true
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
    host_value = mail.get("host")
    mail_host = str(host_value if host_value is not None else "imap.qq.com").strip()
    provider_value = mail.get("provider", mail.get("mail_provider"))
    mail_provider = (
        infer_mail_provider(mail_host)
        if provider_value is None
        else normalize_mail_provider(provider_value)
    )
    return Settings(
        mail_provider=mail_provider,
        mail_host=mail_host,
        mail_port=_coerce_mail_port(mail.get("port", 993)),
        mail_ssl=_coerce_bool(mail.get("ssl", mail.get("mail_ssl", True)), True),
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
provider = "{_toml_string(normalize_mail_provider(settings.mail_provider))}"
host = "{_toml_string(settings.mail_host)}"
port = {settings.mail_port}
ssl = {str(settings.mail_ssl).lower()}
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
    provider_key = next(
        (key for key in ("mail_provider", "provider") if key in payload),
        None,
    )
    host_key = next(
        (key for key in ("mail_host", "host") if key in payload),
        None,
    )
    port_key = next(
        (key for key in ("mail_port", "port") if key in payload),
        None,
    )
    ssl_key = next(
        (key for key in ("mail_ssl", "ssl", "use_ssl") if key in payload),
        None,
    )
    provider = (
        normalize_mail_provider(payload[provider_key])
        if provider_key is not None
        else (
            infer_mail_provider(str(payload[host_key]))
            if host_key is not None
            else current.mail_provider
        )
    )
    if host_key is None:
        host = current.mail_host
        if provider_key is not None and provider != "custom":
            host = mail_provider_preset(provider).host
    else:
        host = str(payload[host_key] or "").strip()
    if not host:
        raise ValueError("IMAP主机不能为空。")
    if port_key is None:
        port = current.mail_port
        if provider_key is not None and provider != "custom":
            port = mail_provider_preset(provider).port
    else:
        port = _coerce_mail_port(payload[port_key], current.mail_port, strict=True)
    mail_ssl = (
        _coerce_bool(payload[ssl_key], current.mail_ssl)
        if ssl_key is not None
        else (
            mail_provider_preset(provider).ssl
            if provider_key is not None and provider != "custom"
            else current.mail_ssl
        )
    )
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
        mail_provider=provider,
        mail_host=host,
        mail_port=port,
        mail_ssl=mail_ssl,
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
