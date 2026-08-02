from __future__ import annotations

import re


# This is intentionally an exact, reviewed alias table. Similar-looking company
# names are not merged automatically because subsidiaries and business units can
# represent separate recruiting processes.
COMPANY_ALIASES = {
    "讯飞招聘": "科大讯飞",
    "京东校招": "京东",
    "OPPO校招": "OPPO",
    "小鹏集团": "小鹏汽车",
    "网易雷火": "网易游戏",
    "网易互娱": "网易游戏",
    "网易游戏雷火": "网易游戏",
    "网易游戏互娱": "网易游戏",
    "网易游戏雷火事业群": "网易游戏",
    "网易游戏互娱事业群": "网易游戏",
    "网易游戏雷火校招": "网易游戏",
    "网易游戏互娱校招": "网易游戏",
    "多益网络招聘": "多益网络",
    "海信集团控股股份有限公司": "海信集团",
}

GENERIC_COMPANY_LABELS = {
    "在线",
    "在线测评",
    "测评",
    "笔试",
    "面试",
    "AI测评",
    "AI",
    "校园招聘",
    "校招",
    "秋招",
    "春招",
    "招聘",
    "招聘通知",
    "招聘团队",
}

GENERIC_COMPANY_PATTERNS = (
    re.compile(r"^(?:20)?\d{2}届?(?:校园招聘|校招|秋招|春招)$", re.IGNORECASE),
    re.compile(r"^(?:在线|AI\s*)?(?:测评|笔试|面试)(?:通知|邀请)?$", re.IGNORECASE),
    re.compile(r"^(?:校园招聘|校招|秋招|春招|招聘)(?:通知|邀请)?$", re.IGNORECASE),
)


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip(" -—_｜|")


def is_generic_company_label(value: str) -> bool:
    candidate = normalize_label(value)
    return candidate in GENERIC_COMPANY_LABELS or any(
        pattern.fullmatch(candidate) for pattern in GENERIC_COMPANY_PATTERNS
    )


def canonical_company(value: str) -> str | None:
    candidate = normalize_label(value)
    if not candidate or is_generic_company_label(candidate):
        return None
    return COMPANY_ALIASES.get(candidate, candidate)
