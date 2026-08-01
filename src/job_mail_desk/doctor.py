from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import CONFIG_PATH, LOCAL_ROOT, Settings, ensure_config
from .credentials import credential_status, load_credential
from .mail_reader import ImapReader


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(settings: Settings, *, online: bool = True) -> list[Check]:
    ensure_config()
    checks = [
        Check("配置文件", CONFIG_PATH.exists(), str(CONFIG_PATH)),
        Check("本地数据目录", LOCAL_ROOT.exists(), str(LOCAL_ROOT)),
        Check("邮箱凭据", credential_status().startswith("已配置"), credential_status()),
        Check(
            "Obsidian 输出",
            not settings.obsidian_enabled or settings.obsidian_output.parent.exists(),
            str(settings.obsidian_output),
        ),
    ]
    if settings.research_enabled:
        checks.append(
            Check(
                "OpenCLI",
                shutil.which("opencli") is not None,
                shutil.which("opencli") or "未找到；仅影响公开研究自动化",
            )
        )
    if online:
        try:
            reader = ImapReader(settings, load_credential())
            before = reader.mailbox_snapshot()
            reader.fetch_since(0)
            after = reader.mailbox_snapshot()
            unchanged = before == after
            checks.append(
                Check(
                    "IMAP 只读连接",
                    unchanged,
                    (
                        "readonly=True + BODY.PEEK；"
                        f"UNSEEN={before['unseen']}；"
                        f"UIDVALIDITY={before['uidvalidity']}；"
                        f"UIDNEXT={before['uidnext']}；"
                        f"扫描后{'未变化' if unchanged else '发生变化'}"
                    ),
                )
            )
        except Exception as exc:
            checks.append(Check("IMAP 只读连接", False, str(exc)))
    return checks


def checks_as_dict(checks: list[Check]) -> list[dict[str, object]]:
    return [asdict(check) for check in checks]
