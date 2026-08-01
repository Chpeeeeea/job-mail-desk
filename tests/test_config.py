from job_mail_desk.config import Settings, load_settings, settings_from_payload, write_settings


def test_core_defaults_do_not_require_obsidian_or_research() -> None:
    settings = Settings()
    assert settings.obsidian_enabled is False
    assert settings.research_enabled is False


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
