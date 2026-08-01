from __future__ import annotations

import getpass
import json
import sys
from dataclasses import dataclass

import keyring
from keyring.errors import KeyringError


SERVICE = "job-mail-desk.mail"
USERNAME = "default-imap"
LEGACY_SERVICE = "job-mail-watch.qqmail"
LEGACY_USERNAME = "qqmail-imap"


def _credential_store_name() -> str:
    return "macOS Keychain" if sys.platform == "darwin" else "Windows 凭据库"


@dataclass(frozen=True)
class MailCredential:
    email: str
    authorization_code: str


def _validate_code(value: str) -> str:
    code = value.strip()
    if not code:
        raise ValueError("授权码不能为空。")
    if not code.isascii() or any(character.isspace() for character in code):
        raise ValueError("授权码只能包含不带空格的 ASCII 字符。")
    if len(code) < 8:
        raise ValueError("授权码长度异常。")
    return code


def configure_interactively() -> None:
    email_address = input("邮箱地址：").strip()
    if "@" not in email_address or not email_address.isascii():
        raise ValueError("请输入完整邮箱地址。")
    code = _validate_code(getpass.getpass("IMAP 授权码（不回显）："))
    confirmation = _validate_code(getpass.getpass("再次输入授权码（不回显）："))
    if code != confirmation:
        raise ValueError("两次输入不一致，未保存。")
    save_credential(email_address, code)
    print(f"凭据已保存到{_credential_store_name()}（授权码长度：{len(code)}）。")


def save_credential(email_address: str, authorization_code: str) -> None:
    email_address = email_address.strip()
    if "@" not in email_address or not email_address.isascii():
        raise ValueError("请输入完整邮箱地址。")
    code = _validate_code(authorization_code)
    keyring.set_password(
        SERVICE,
        USERNAME,
        json.dumps(
            {"email": email_address, "authorization_code": code},
            ensure_ascii=False,
        ),
    )


def _load_payload(service: str, username: str) -> str | None:
    try:
        return keyring.get_password(service, username)
    except KeyringError as exc:
        raise RuntimeError(f"无法访问{_credential_store_name()}：{exc}") from exc


def load_credential() -> MailCredential:
    payload = _load_payload(SERVICE, USERNAME)
    if not payload:
        payload = _load_payload(LEGACY_SERVICE, LEGACY_USERNAME)
    if not payload:
        raise RuntimeError("尚未配置邮箱凭据。")
    try:
        parsed = json.loads(payload)
        email_address = str(parsed["email"])
        code = _validate_code(str(parsed["authorization_code"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{_credential_store_name()}中的邮箱配置无效。") from exc
    return MailCredential(email=email_address, authorization_code=code)


def credential_status() -> str:
    try:
        credential = load_credential()
    except RuntimeError:
        return "未配置"
    local, _, domain = credential.email.partition("@")
    masked = local[:2] + "*" * max(2, len(local) - 2)
    return f"已配置：{masked}@{domain}"
