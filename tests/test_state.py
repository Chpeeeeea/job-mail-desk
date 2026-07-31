from job_mail_desk.state import StateStore


def test_duplicate_message_hash_is_processed_once(tmp_path) -> None:
    state = StateStore(tmp_path / "state.db")
    assert not state.is_processed("abc")
    state.mark_processed("abc", "task-1")
    state.mark_processed("abc", "task-2")
    assert state.is_processed("abc")
