import pytest

from job_mail_desk.state import StateStore, StateVersionMismatch


def test_duplicate_message_hash_is_processed_once(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    assert not state.is_processed("abc")
    state.mark_processed("abc", "task-1")
    state.mark_processed("abc", "task-2")
    assert state.is_processed("abc")


def test_parser_version_change_replays_once(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    state.mark_processed("abc", "task-1")
    assert state.prepare_parser_version("v1") is True
    assert state.is_processed("abc")
    state.mark_processed("abc", "task-1")
    assert state.prepare_parser_version("v1") is False
    assert state.is_processed("abc")
    with pytest.raises(StateVersionMismatch):
        state.prepare_parser_version("v2")
    assert state.is_processed("abc")


def test_successful_scan_state_ignores_failed_runs(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    assert not state.has_successful_scan()
    failed = state.begin_scan()
    state.finish_scan(failed, fetched=1, candidates=0, error="blocked")
    assert not state.has_successful_scan()
    completed = state.begin_scan()
    state.finish_scan(completed, fetched=1, candidates=1)
    assert state.has_successful_scan()


def test_new_version_state_inherits_only_compatible_dedup_baseline(tmp_path) -> None:
    old = StateStore(tmp_path / "state-frozen-v0.6.0-pparser-v1.db")
    old.prepare_parser_version("parser-v1")
    old.mark_processed("mail-one", "task-one")
    old.mark_processed("mail-two", None)

    incompatible = StateStore(tmp_path / "state-frozen-v0.5.0-pparser-v0.db")
    incompatible.prepare_parser_version("parser-v0")
    incompatible.mark_processed("old-parser-mail", None)

    current = StateStore(tmp_path / "state-frozen-v0.6.1-pparser-v1.db")
    current.prepare_parser_version("parser-v1")
    imported = current.bootstrap_processed_from(
        [incompatible.path, old.path],
        parser_version="parser-v1",
    )

    assert imported == 2
    assert current.is_processed("mail-one")
    assert current.is_processed("mail-two")
    assert not current.is_processed("old-parser-mail")
    assert current.bootstrap_processed_from(
        [old.path], parser_version="parser-v1"
    ) == 0
