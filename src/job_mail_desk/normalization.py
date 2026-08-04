from __future__ import annotations

import re


# This is intentionally an exact, reviewed alias table. Similar-looking company
# names are not merged automatically because subsidiaries and business units can
# represent separate recruiting processes.
COMPANY_ALIASES = {
    "百度招聘": "百度",
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
    "帆软招聘": "帆软",
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


ROLE_ALIASES = {
    "tet综合方向": "TET 综合方向",
    "tet管理培训生综合方向": "TET 综合方向",
    "tet管培生综合方向": "TET 综合方向",
}


def is_invalid_role(value: str | None) -> bool:
    if not value:
        return False
    if re.search(r"(?:事业群|校园)?校招(?:职位|岗位)?$", value.strip()):
        return True
    return bool(
        re.search(
            r"https?://|www\.|\.com(?:/|\b)|官网|个人中心|应聘记录|"
            r"进行修改|点击(?:链接|进入)|查询网申进度",
            value,
            re.IGNORECASE,
        )
    )


def role_key(value: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).casefold()
    cleaned = re.sub(r"[（(]?[A-Za-z]\d{4,}[）)]?", "", cleaned)
    return cleaned


def canonical_role(value: str | None) -> str | None:
    if not value or is_invalid_role(value):
        return None
    candidate = normalize_label(value)
    key = role_key(candidate)
    if re.search(r"tet.*综合方向", key, re.IGNORECASE):
        return "TET 综合方向"
    return ROLE_ALIASES.get(key, candidate)


def roles_equivalent(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    left_role = canonical_role(left)
    right_role = canonical_role(right)
    return bool(
        left_role
        and right_role
        and role_key(left_role) == role_key(right_role)
    )


def normalize_company_project(
    company: str,
    project: str | None = None,
) -> tuple[str, str | None]:
    raw_company = normalize_label(company)
    normalized_company = canonical_company(raw_company) or raw_company
    normalized_project = normalize_label(project) if project else None
    if "雷火" in raw_company and not (normalized_project and "雷火事业群" in normalized_project):
        normalized_project = (
            f"雷火事业群 · {normalized_project}"
            if normalized_project
            else "雷火事业群"
        )
    elif "互娱" in raw_company and not (normalized_project and "互娱事业群" in normalized_project):
        normalized_project = (
            f"互娱事业群 · {normalized_project}"
            if normalized_project
            else "互娱事业群"
        )
    return normalized_company, normalized_project
