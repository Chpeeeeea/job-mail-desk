from job_mail_desk.state import StateStore


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
    assert not state.is_processed("abc")
    state.mark_processed("abc", "task-1")
    assert state.prepare_parser_version("v1") is False
    assert state.is_processed("abc")
    assert state.prepare_parser_version("v2") is True
    assert not state.is_processed("abc")
