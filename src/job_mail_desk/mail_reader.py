from __future__ import annotations

import imaplib
from datetime import date, datetime, timedelta
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .config import Settings
from .credentials import MailCredential
from .models import MailRecord


SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_MESSAGE_BYTES = 512_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(value: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(value)
    return " ".join(extractor.parts)


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for content, encoding in decode_header(value):
        if isinstance(content, bytes):
            parts.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(content)
    return "".join(parts)


def _message_body(message: EmailMessage) -> str:
    plain: list[str] = []
    html: list[str] = []
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content())
        except (LookupError, UnicodeDecodeError):
            raw = part.get_payload(decode=True) or b""
            content = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plain if content_type == "text/plain" else html).append(content)
    return "\n".join(plain) if plain else _html_to_text("\n".join(html))


def parse_message(uid: str, raw: bytes) -> MailRecord:
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    received = parsedate_to_datetime(parsed.get("Date")) if parsed.get("Date") else None
    if received is None:
        received = datetime.now(SHANGHAI)
    elif received.tzinfo is None:
        received = received.replace(tzinfo=SHANGHAI)
    return MailRecord(
        uid=uid,
        subject=_decode_header(parsed.get("Subject")),
        message_id=str(parsed.get("Message-ID") or "").strip(),
        sender=_decode_header(parsed.get("From")),
        received_at=received.astimezone(SHANGHAI),
        body=_message_body(parsed),
    )


class ImapReader:
    def __init__(self, settings: Settings, credential: MailCredential) -> None:
        self.settings = settings
        self.credential = credential

    def fetch_since(self, days: int | None = None) -> list[MailRecord]:
        lookback = days if days is not None else self.settings.lookback_days
        since_date: date = datetime.now(SHANGHAI).date() - timedelta(days=lookback)
        records: list[MailRecord] = []
        with imaplib.IMAP4_SSL(
            self.settings.mail_host,
            self.settings.mail_port,
        ) as client:
            client.login(
                self.credential.email,
                self.credential.authorization_code,
            )
            status, _ = client.select(self.settings.mail_folder, readonly=True)
            if status != "OK":
                raise RuntimeError("无法以只读方式打开邮箱文件夹。")
            status, data = client.uid(
                "search",
                None,
                "SINCE",
                since_date.strftime("%d-%b-%Y"),
            )
            if status != "OK":
                raise RuntimeError("IMAP 搜索失败。")
            for raw_uid in data[0].split() if data and data[0] else []:
                status, fetched = client.uid(
                    "fetch",
                    raw_uid,
                    f"(BODY.PEEK[]<0.{MAX_MESSAGE_BYTES}>)",
                )
                if status != "OK":
                    continue
                body = next(
                    (
                        item[1]
                        for item in fetched
                        if isinstance(item, tuple) and isinstance(item[1], bytes)
                    ),
                    None,
                )
                if body:
                    records.append(parse_message(raw_uid.decode("ascii"), body))
        return records

    def mailbox_snapshot(self) -> dict[str, str | int | None]:
        """Read mailbox invariants without changing flags or UID state."""
        with imaplib.IMAP4_SSL(
            self.settings.mail_host,
            self.settings.mail_port,
        ) as client:
            client.login(
                self.credential.email,
                self.credential.authorization_code,
            )
            status, _ = client.select(self.settings.mail_folder, readonly=True)
            if status != "OK":
                raise RuntimeError("无法以只读方式打开邮箱文件夹。")
            unseen_status, unseen_data = client.uid("search", None, "UNSEEN")
            unseen = (
                len(unseen_data[0].split())
                if unseen_status == "OK" and unseen_data and unseen_data[0]
                else 0
            )

            def response_value(name: str) -> str | None:
                _, values = client.response(name)
                if not values:
                    return None
                value = values[-1]
                return value.decode("ascii", errors="replace") if isinstance(value, bytes) else str(value)

            return {
                "unseen": unseen,
                "uidvalidity": response_value("UIDVALIDITY"),
                "uidnext": response_value("UIDNEXT"),
            }
