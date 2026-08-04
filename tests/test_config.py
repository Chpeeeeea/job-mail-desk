import pytest

from job_mail_desk.config import (
    MAIL_PROVIDER_PRESETS,
    Settings,
    load_settings,
    settings_from_payload,
    write_settings,
)


def test_core_defaults_do_not_require_obsidian_or_research() -> None:
    settings = Settings()
    assert settings.obsidian_enabled is False
    assert settings.research_enabled is False
    assert settings.updates_enabled is True
    assert settings.update_channel == "preview"


def test_settings_round_trip_paths_and_intervals(tmp_path) -> None:
    current = Settings()
    updated = settings_from_payload(
        current,
        {
            "poll_minutes": 15,
            "lookback_days": 7,
            "obsidian_enabled": True,
            "obsidian_output": str(tmp_path / "Mobile" / "待办.md"),
            "progress_enabled": True,
            "progress_output": str(tmp_path / "进展.md"),
            "progress_source": str(tmp_path / "台账.md"),
            "updates_enabled": False,
            "update_channel": "stable",
        },
    )
    config = tmp_path / "config.toml"
    write_settings(updated, config)
    loaded = load_settings(config)
    assert loaded.poll_minutes == 15
    assert loaded.lookback_days == 7
    assert loaded.obsidian_output == tmp_path / "Mobile" / "待办.md"
    assert loaded.progress_output == tmp_path / "进展.md"
    assert loaded.progress_source == tmp_path / "台账.md"
    assert loaded.research_enabled is False
    assert loaded.updates_enabled is False
    assert loaded.update_channel == "stable"


def test_legacy_research_switch_is_ignored_by_core(tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[research]\nenabled = true\n", encoding="utf-8")

    assert load_settings(config).research_enabled is False


def test_mail_provider_defaults_cover_supported_choices() -> None:
    assert set(MAIL_PROVIDER_PRESETS) == {
        "qq",
        "163",
        "126",
        "yeah",
        "gmail",
        "outlook",
        "custom",
    }
    assert MAIL_PROVIDER_PRESETS["qq"].host == "imap.qq.com"
    assert MAIL_PROVIDER_PRESETS["outlook"].port == 993
    assert all(preset.ssl for preset in MAIL_PROVIDER_PRESETS.values())


def test_legacy_mail_config_infers_provider_from_host(tmp_path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[mail]\nhost = "imap.qq.com"\nport = 993\n',
        encoding="utf-8",
    )
    loaded = load_settings(config)
    assert loaded.mail_provider == "qq"
    assert loaded.mail_host == "imap.qq.com"
    assert loaded.mail_ssl is True

    config.write_text(
        '[mail]\nhost = "imap.163.com"\nport = 993\n',
        encoding="utf-8",
    )
    assert load_settings(config).mail_provider == "163"

    config.write_text(
        '[mail]\nhost = "mx.example.test"\nport = 993\n',
        encoding="utf-8",
    )
    assert load_settings(config).mail_provider == "custom"


def test_custom_mail_settings_round_trip_and_validate_port(tmp_path) -> None:
    updated = settings_from_payload(
        Settings(),
        {
            "mail_provider": "custom",
            "mail_host": "mx.example.test",
            "mail_port": 587,
            "mail_ssl": False,
            "poll_minutes": 10,
            "lookback_days": 3,
            "update_channel": "preview",
        },
    )
    config = tmp_path / "config.toml"
    write_settings(updated, config)
    loaded = load_settings(config)
    assert loaded.mail_provider == "custom"
    assert loaded.mail_host == "mx.example.test"
    assert loaded.mail_port == 587
    assert loaded.mail_ssl is False

    with pytest.raises(ValueError):
        settings_from_payload(
            Settings(),
            {
                "mail_provider": "custom",
                "mail_host": "mx.example.test",
                "mail_port": 65536,
                "mail_ssl": True,
                "poll_minutes": 10,
                "lookback_days": 3,
                "update_channel": "preview",
            },
        )
