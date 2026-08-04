from contextlib import nullcontext
from datetime import datetime
from email.message import EmailMessage

from job_mail_desk.config import Settings
from job_mail_desk.credentials import MailCredential
from job_mail_desk.mail_reader import ImapReader
from job_mail_desk.parser import SHANGHAI


class FakeImap:
    instance = None

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.readonly = None
        self.fetch_query = None
        FakeImap.instance = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, email, code):
        return "OK", []

    def select(self, folder, readonly=False):
        self.readonly = readonly
        return "OK", [b"1"]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b"42"]
        if command == "fetch":
            self.fetch_query = args[-1]
            message = EmailMessage()
            message["Subject"] = "【样例】笔试通知"
            message["From"] = "noreply@example.invalid"
            message["Date"] = datetime.now(SHANGHAI)
            message.set_content("笔试时间待确认")
            return "OK", [(b"42", message.as_bytes())]
        raise AssertionError(command)


def test_imap_uses_readonly_and_body_peek(monkeypatch) -> None:
    monkeypatch.setattr("job_mail_desk.mail_reader.imaplib.IMAP4_SSL", FakeImap)
    records = ImapReader(
        Settings(),
        MailCredential("private@example.invalid", "authorization-code"),
    ).fetch_since(1)
    assert len(records) == 1
    assert FakeImap.instance.readonly is True
    assert "BODY.PEEK" in FakeImap.instance.fetch_query


def test_imap_can_use_plain_connection_when_ssl_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr("job_mail_desk.mail_reader.imaplib.IMAP4", FakeImap)
    records = ImapReader(
        Settings(mail_ssl=False),
        MailCredential("private@example.invalid", "authorization-code"),
    ).fetch_since(1)
    assert len(records) == 1
    assert FakeImap.instance.readonly is True
    assert "BODY.PEEK" in FakeImap.instance.fetch_query

