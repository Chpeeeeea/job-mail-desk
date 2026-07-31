from pathlib import Path

from job_mail_desk.ui_app import _open_obsidian_uri, _paper_url


def test_obsidian_button_uses_obsidian_uri(monkeypatch) -> None:
    opened = []
    monkeypatch.setattr(
        "job_mail_desk.ui_app.webbrowser.open",
        lambda value: opened.append(value),
    )
    _open_obsidian_uri(Path("D:/Vault/Mobile/求职硬截止待办集.md"))
    assert opened
    assert opened[0].startswith("obsidian://open?")
    assert "vault=Mobile" in opened[0]
    assert ".md" not in opened[0]


def test_paper_id_uses_fragment_not_file_query() -> None:
    url = _paper_url("paper123")
    assert url.endswith("paper.html#paper=paper123")
    assert "%3Fpaper" not in url
