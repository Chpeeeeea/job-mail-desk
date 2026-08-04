from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .markdown_store import _atomic_write
from .privacy import redact_text


def _safe(value: object, limit: int = 120) -> str:
    text = redact_text(str(value or ""))
    text = re.sub(r"https?://\S+", "[链接已隐藏]", text)
    text = text.replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or "—"


def export_identity_preview(summary, path: Path) -> Path:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "---",
        "title: JobMailDesk Identity Resolver 人工验收预览",
        "type: jobmaildesk-identity-preview",
        f"generated_at: {generated_at}",
        "readonly: true",
        "---",
        "",
        "# Identity Resolver 人工验收预览",
        "",
        "> 本文件由只读邮箱影子扫描生成，不修改任务、扫描状态或邮件。",
        "> 仅包含结构化字段，不包含邮件正文、发件人地址、私人链接或认证参数。",
        "",
        "## 汇总",
        "",
        f"- 获取邮件：{summary.fetched}",
        f"- 招聘候选：{summary.candidates}",
        f"- 唯一归属：{summary.identity_matched}",
        f"- 建议新申请：{summary.identity_new_applications}",
        f"- 待归属：{summary.identity_unresolved}",
        f"- 硬冲突：{summary.identity_conflicts}",
        f"- 解析失败：{summary.parse_failed}",
        "",
        "## 逐条判断",
        "",
        "| # | 公司 | 岗位 | 项目 | 阶段 | 判断 | 原因 | 申请键 |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(summary.preview, start=1):
        lines.append(
            "| "
            + " | ".join(
                (
                    str(index),
                    _safe(item.get("company"), 50),
                    _safe(item.get("role"), 80),
                    _safe(item.get("project"), 50),
                    _safe(item.get("stage"), 30),
                    _safe(item.get("identity_action"), 30),
                    _safe(item.get("resolution_reason"), 40),
                    _safe(item.get("application_key"), 40),
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            "## 人工验收重点",
            "",
            "- `matched` / `batch_context_match` 是否指向正确申请。",
            "- `unresolved` 是否确实缺少唯一身份，不能自动判断。",
            "- `new_application` 是否真的是新的独立投递。",
            "- JDS/TET、雷火/互娱以及不同职位编号是否保持分离。",
            "",
            "确认前不要启用正式 Registry 写入或 unresolved 持久化。",
            "",
        )
    )
    _atomic_write(path, "\n".join(lines))
    return path
