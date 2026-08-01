from __future__ import annotations

import json
import platform
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import __version__
from .config import LOCAL_ROOT


REPOSITORY = "Chpeeeeea/job-mail-desk"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
UPDATE_ROOT = LOCAL_ROOT / "updates"
UPDATE_STATE = UPDATE_ROOT / "state.json"
CHECK_INTERVAL = timedelta(hours=24)
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateDescriptor:
    version: str
    tag: str
    title: str
    notes: str
    release_url: str
    published_at: str
    asset_name: str
    checksum_name: str

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "tag": self.tag,
            "title": self.title,
            "notes": self.notes,
            "release_url": self.release_url,
            "published_at": self.published_at,
            "asset_name": self.asset_name,
            "checksum_name": self.checksum_name,
        }


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"不支持的版本号：{value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def release_platform(
    system: str | None = None,
    machine: str | None = None,
) -> str:
    system_name = (system or platform.system()).lower()
    machine_name = (machine or platform.machine()).lower()
    if system_name == "windows" and machine_name in {"amd64", "x86_64"}:
        return "win-x64"
    if system_name == "darwin" and machine_name in {"arm64", "aarch64"}:
        return "macos-arm64"
    if system_name == "darwin" and machine_name in {"amd64", "x86_64"}:
        return "macos-x64"
    raise UpdateError(f"当前平台暂不支持版本通知：{system_name}/{machine_name}")


def _request_json(url: str, *, timeout: float = 12) -> list[dict[str, object]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"JobMailDesk/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise UpdateError(f"无法连接 GitHub Release：{exc}") from exc
    if not isinstance(payload, list):
        raise UpdateError("GitHub Release 返回了无法识别的数据。")
    return [item for item in payload if isinstance(item, dict)]


def _safe_release_url(url: str) -> bool:
    return url.startswith(f"https://github.com/{REPOSITORY}/releases/")


def find_update(
    *,
    channel: str = "preview",
    current_version: str = __version__,
    releases: list[dict[str, object]] | None = None,
    platform_name: str | None = None,
) -> UpdateDescriptor | None:
    if channel not in {"stable", "preview"}:
        raise ValueError("更新通道必须是 stable 或 preview。")
    current = parse_version(current_version)
    target_platform = platform_name or release_platform()
    candidates = releases if releases is not None else _request_json(RELEASES_API)
    ranked: list[tuple[tuple[int, int, int], dict[str, object]]] = []
    for release in candidates:
        if release.get("draft"):
            continue
        if channel == "stable" and release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "")
        try:
            version = parse_version(tag)
        except ValueError:
            continue
        if version > current:
            ranked.append((version, release))
    for version_tuple, release in sorted(ranked, key=lambda item: item[0], reverse=True):
        version = ".".join(str(part) for part in version_tuple)
        archive_name = f"JobMailDesk-Core-v{version}-{target_platform}.zip"
        checksum_name = f"{archive_name}.sha256"
        asset_names = {
            str(asset.get("name") or "")
            for asset in release.get("assets", [])
            if isinstance(asset, dict)
        }
        if archive_name not in asset_names or checksum_name not in asset_names:
            continue
        release_url = str(release.get("html_url") or "")
        if not _safe_release_url(release_url):
            raise UpdateError("Release 页面未通过仓库来源校验。")
        return UpdateDescriptor(
            version=version,
            tag=str(release.get("tag_name") or f"v{version}"),
            title=str(release.get("name") or f"JobMailDesk Core v{version}"),
            notes=str(release.get("body") or ""),
            release_url=release_url,
            published_at=str(release.get("published_at") or ""),
            asset_name=archive_name,
            checksum_name=checksum_name,
        )
    return None


def _read_state(path: Path = UPDATE_STATE) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(payload: dict[str, object], path: Path = UPDATE_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


class UpdateManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict[str, object] = {
            "state": "idle",
            "current_version": __version__,
            "release_url": RELEASES_PAGE,
        }
        self._available: UpdateDescriptor | None = None

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._status)

    def _set(self, **values: object) -> None:
        with self._lock:
            self._status.update(values)

    def start_check(self, channel: str, *, manual: bool = True) -> bool:
        with self._lock:
            if self._status["state"] == "checking":
                return False
            self._status = {
                "state": "checking",
                "current_version": __version__,
                "manual": manual,
                "release_url": RELEASES_PAGE,
            }
        threading.Thread(
            target=self._check_worker,
            args=(channel,),
            daemon=True,
        ).start()
        return True

    def maybe_check(self, channel: str) -> bool:
        payload = _read_state()
        checked = str(payload.get("last_checked_at") or "")
        if checked:
            try:
                last_checked = datetime.fromisoformat(checked)
                if (
                    datetime.now(UTC) - last_checked < CHECK_INTERVAL
                    and payload.get("channel") == channel
                ):
                    cached = payload.get("available")
                    if isinstance(cached, dict):
                        try:
                            descriptor = UpdateDescriptor(**cached)
                            if (
                                parse_version(descriptor.version) > parse_version(__version__)
                                and _safe_release_url(descriptor.release_url)
                            ):
                                self._available = descriptor
                                self._set(state="available", **descriptor.to_dict())
                        except (TypeError, ValueError):
                            pass
                    return False
            except ValueError:
                pass
        return self.start_check(channel, manual=False)

    def _check_worker(self, channel: str) -> None:
        try:
            descriptor = find_update(channel=channel)
            _write_state(
                {
                    "last_checked_at": datetime.now(UTC).isoformat(),
                    "channel": channel,
                    "available": descriptor.__dict__ if descriptor else None,
                }
            )
            self._available = descriptor
            if descriptor:
                self._set(state="available", **descriptor.to_dict())
            else:
                self._set(state="up_to_date", detail="当前已是最新版本。")
        except Exception as exc:
            self._set(state="error", detail=str(exc))

    def release_url(self) -> str:
        with self._lock:
            return str(self._status.get("release_url") or RELEASES_PAGE)
