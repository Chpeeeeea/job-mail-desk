from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
# Standalone long numbers are sensitive; numeric runs inside hashes/IDs are not.
LONG_NUMBER_PATTERN = re.compile(r"(?<![\w])\d{6,}(?![\w])")
TOKEN_LABEL_PATTERN = re.compile(
    r"(?i)(通行证|验证码|授权码|密码|口令|token|code)\s*[:：]?\s*[A-Za-z0-9_-]{4,}"
)
AUTH_QUERY_NAMES = {
    "token",
    "auth",
    "code",
    "key",
    "signature",
    "sign",
    "xsec_token",
    "session",
    "ticket",
}


def redact_text(value: str) -> str:
    value = EMAIL_PATTERN.sub("[邮箱已隐藏]", value)
    value = PHONE_PATTERN.sub("[手机号已隐藏]", value)
    value = TOKEN_LABEL_PATTERN.sub(lambda match: f"{match.group(1)}：[已隐藏]", value)
    value = LONG_NUMBER_PATTERN.sub("[敏感数字已隐藏]", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_public_terms(*values: str | None) -> list[str]:
    terms: list[str] = []
    for value in values:
        if not value:
            continue
        redacted = redact_text(value)
        redacted = re.sub(r"https?://\S+", "", redacted)
        if redacted and "[" not in redacted:
            terms.append(redacted)
    return terms


def sanitized_url(value: str | None, *, remove_all_query: bool = True) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    query = ""
    if not remove_all_query and parsed.query:
        pairs = []
        for part in parsed.query.split("&"):
            name = part.partition("=")[0].lower()
            if name not in AUTH_QUERY_NAMES:
                pairs.append(part)
        query = "&".join(pairs)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def contains_sensitive_public_data(payload: str) -> bool:
    return bool(
        EMAIL_PATTERN.search(payload)
        or PHONE_PATTERN.search(payload)
        or LONG_NUMBER_PATTERN.search(payload)
        or re.search(r"https?://", payload)
    )
