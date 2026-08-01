from __future__ import annotations

from datetime import UTC, datetime

import pytest

from job_mail_desk.updates import (
    UpdateError,
    UpdateManager,
    find_update,
    parse_version,
    release_platform,
)


def _release(version: str, *, prerelease: bool = True) -> dict[str, object]:
    prefix = f"JobMailDesk-Core-v{version}-win-x64.zip"
    base = (
        "https://github.com/Chpeeeeea/job-mail-desk/releases/download/"
        f"v{version}/"
    )
    return {
        "tag_name": f"v{version}",
        "name": f"JobMailDesk Core v{version}",
        "body": "更新说明",
        "html_url": base.rstrip("/"),
        "published_at": "2026-08-02T00:00:00Z",
        "draft": False,
        "prerelease": prerelease,
        "assets": [
            {
                "name": prefix,
                "browser_download_url": base + prefix,
                "size": 1024,
                "digest": "sha256:" + "a" * 64,
            },
            {
                "name": prefix + ".sha256",
                "browser_download_url": base + prefix + ".sha256",
                "size": 100,
            },
        ],
    }


def test_version_and_platform_selection() -> None:
    assert parse_version("v0.4.1") == (0, 4, 1)
    assert release_platform("Windows", "AMD64") == "win-x64"
    assert release_platform("Darwin", "arm64") == "macos-arm64"
    assert release_platform("Darwin", "x86_64") == "macos-x64"
    with pytest.raises(UpdateError):
        release_platform("Windows", "arm64")


def test_preview_and_stable_channels_are_separate() -> None:
    releases = [_release("0.5.0", prerelease=True), _release("0.4.1", prerelease=False)]
    preview = find_update(
        current_version="0.4.0",
        channel="preview",
        releases=releases,
        platform_name="win-x64",
    )
    stable = find_update(
        current_version="0.4.0",
        channel="stable",
        releases=releases,
        platform_name="win-x64",
    )
    assert preview and preview.version == "0.5.0"
    assert stable and stable.version == "0.4.1"
    assert find_update(
        current_version="0.5.0",
        channel="preview",
        releases=releases,
        platform_name="win-x64",
    ) is None


def test_release_asset_must_come_from_project_repository() -> None:
    release = _release("0.4.1", prerelease=False)
    release["html_url"] = "https://example.com/releases/tag/v0.4.1"
    with pytest.raises(UpdateError, match="来源校验"):
        find_update(
            current_version="0.4.0",
            releases=[release],
            platform_name="win-x64",
        )

def test_daily_check_restores_cached_available_release(monkeypatch) -> None:
    monkeypatch.setattr("job_mail_desk.updates.__version__", "0.4.0")
    descriptor = find_update(
        current_version="0.4.0",
        releases=[_release("0.4.1")],
        platform_name="win-x64",
    )
    assert descriptor
    monkeypatch.setattr(
        "job_mail_desk.updates._read_state",
        lambda: {
            "last_checked_at": datetime.now(UTC).isoformat(),
            "channel": "preview",
            "available": descriptor.__dict__,
        },
    )
    manager = UpdateManager()
    assert manager.maybe_check("preview") is False
    assert manager.status()["state"] == "available"
    assert manager.status()["version"] == "0.4.1"
