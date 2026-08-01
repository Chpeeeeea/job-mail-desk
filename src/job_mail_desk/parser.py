from __future__ import annotations

import re
from datetime import datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from .models import MailRecord, ParsedEvent
from .privacy import redact_text


SHANGHAI = ZoneInfo("Asia/Shanghai")
PARSER_VERSION = "2026.08.01.5"
URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+")
RECRUITING_KEYWORDS = (
    "笔试",
    "测评",
    "AI面试",
    "AI 面试",
    "面试",
    "材料提交",
    "截止",
    "校园招聘",
    "校招",
    "秋招",
    "春招",
    "招聘",
    "应聘",
    "offer",
    "录用",
    "未通过",
    "感谢投递",
    "感谢您投递",
    "完善简历",
)
STAGES = (
    ("简历完善", ("完善简历信息", "完善简历", "更新简历信息")),
    ("Offer", ("offer", "录用通知", "录用意向")),
    ("未通过", ("未通过", "遗憾通知", "不匹配")),
    ("在线笔试", ("在线笔试", "笔试")),
    ("人才测评", ("人才测评", "在线测评", "测评")),
    ("AI 面试", ("AI面试", "AI 面试")),
    ("HR 面试", ("HR面", "HR 面", "人力面试")),
    ("面试", ("面试邀请", "面试安排", "业务面", "面试")),
    ("材料截止", ("材料提交", "材料补充", "提交材料")),
    ("网申", ("网申", "申请成功", "感谢投递", "感谢您投递")),
)
FULL_RANGE = re.compile(
    r"(?P<sy>20\d{2})[年./-](?P<sm>\d{1,2})[月./-](?P<sd>\d{1,2})[日号]?"
    r"[^\d]{0,12}(?P<sh>[01]?\d|2[0-3]|24)[:：](?P<smin>[0-5]\d)(?::[0-5]\d)?"
    r"\s*(?:至|到|—|–|-|~|～)\s*"
    r"(?P<ey>20\d{2})[年./-](?P<em>\d{1,2})[月./-](?P<ed>\d{1,2})[日号]?"
    r"[^\d]{0,12}(?P<eh>[01]?\d|2[0-3]|24)[:：](?P<emin>[0-5]\d)(?::[0-5]\d)?"
)
SAME_DAY_RANGE = re.compile(
    r"(?:(?P<y>20\d{2})[年./-])?(?P<m>\d{1,2})[月./-](?P<d>\d{1,2})[日号]?"
    r"[^\d]{0,12}(?P<sh>[01]?\d|2[0-3]|24)[:：](?P<smin>[0-5]\d)"
    r"\s*(?:至|到|—|–|-|~|～)\s*(?P<eh>[01]?\d|2[0-3]|24)[:：](?P<emin>[0-5]\d)"
)
DATETIME = re.compile(
    r"(?:(?P<y>20\d{2})[年./-])?(?P<m>\d{1,2})[月./-](?P<d>\d{1,2})[日号]?"
    r"[^\d]{0,12}(?P<h>[01]?\d|2[0-3]|24)[:：](?P<min>[0-5]\d)"
)
CN_DATETIME = re.compile(
    r"(?:(?P<y>20\d{2})[年./-])?(?P<m>\d{1,2})[月./-](?P<d>\d{1,2})[日号]?"
    r"[^\d]{0,12}(?P<h>[01]?\d|2[0-3]|24)\s*点(?:\s*(?P<min>[0-5]?\d)\s*分)?"
)
ROLE_PATTERNS = (
    re.compile(r"(?:邀请您参加|邀请你参加)\s*([^，。\n]{2,60}?)\s*岗位"),
    re.compile(r"感谢您投递[^\n，。]{2,120}[）)]([^，。]{2,40})，现邀请"),
    re.compile(r"(?:面试职位|应聘职位|职位名称|应聘岗位|岗位名称)\s*[:：]\s*([^\n。；]{2,60})"),
    re.compile(r"(?:岗位|职位)\s*[:：]\s*([^\n。；]{2,60})"),
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def _year(explicit: str | None, month: int, day: int, received: datetime) -> int:
    if explicit:
        return int(explicit)
    candidate = datetime(received.year, month, day, tzinfo=SHANGHAI)
    return received.year + 1 if candidate < received - timedelta(days=180) else received.year


def _dt(
    year: str | None,
    month: str,
    day: str,
    hour: str,
    minute: str,
    received: datetime,
) -> datetime:
    parsed_hour = int(hour)
    value = datetime(
        _year(year, int(month), int(day), received),
        int(month),
        int(day),
        0 if parsed_hour == 24 else parsed_hour,
        int(minute),
        tzinfo=SHANGHAI,
    )
    return value + timedelta(days=1) if parsed_hour == 24 else value


def _times(
    text: str,
    received: datetime,
) -> tuple[datetime | None, datetime | None, datetime | None]:
    start = end = deadline = None
    full = FULL_RANGE.search(text)
    same = SAME_DAY_RANGE.search(text) if not full else None
    if full:
        g = full.groupdict()
        start = _dt(g["sy"], g["sm"], g["sd"], g["sh"], g["smin"], received)
        end = _dt(g["ey"], g["em"], g["ed"], g["eh"], g["emin"], received)
    elif same:
        g = same.groupdict()
        start = _dt(g["y"], g["m"], g["d"], g["sh"], g["smin"], received)
        end_hour = int(g["eh"])
        end = start.replace(
            hour=0 if end_hour == 24 else end_hour,
            minute=int(g["emin"]),
        )
        if end_hour == 24:
            end += timedelta(days=1)
        if end <= start:
            end += timedelta(days=1)
    datetime_matches = [*DATETIME.finditer(text), *CN_DATETIME.finditer(text)]
    datetime_matches.sort(key=lambda item: item.start())
    for match in datetime_matches:
        g = match.groupdict()
        candidate = _dt(
            g["y"],
            g["m"],
            g["d"],
            g["h"],
            g.get("min") or "00",
            received,
        )
        before = text[max(0, match.start() - 36) : match.start()]
        after = text[match.end() : match.end() + 20]
        deadline_before = re.search(
            r"(?:截止(?:时间)?|有效期至|最晚|请在|须在|务必在)[^。；;]{0,30}$",
            before,
        )
        deadline_after = re.search(
            r"^\s*(?:之前|前(?:\s|完成|[，,。；;])|失效|到期|过期)",
            after,
        )
        if deadline_before or deadline_after:
            deadline = candidate
        elif re.search(r"^\s*生效", after) or start is None:
            start = candidate
    if start and deadline and re.search(r"生效", text) and re.search(r"失效", text):
        end, deadline = deadline, None
    return start, end, deadline


def _stage(subject: str, body: str) -> str:
    for text in (subject, body):
        lowered = text.lower()
        for stage, keywords in STAGES:
            if any(keyword.lower() in lowered for keyword in keywords):
                return stage
    return "招聘通知"


def _event_type(stage: str) -> str:
    return {
        "Offer": "offer",
        "未通过": "rejection",
        "在线笔试": "assessment",
        "人才测评": "assessment",
        "AI 面试": "interview",
        "HR 面试": "interview",
        "面试": "interview",
        "材料截止": "deadline",
        "简历完善": "deadline",
        "网申": "application",
    }.get(stage, "notice")


def _change(subject: str, body: str) -> str:
    if re.search(r"取消|作废|无需参加", subject):
        return "cancel"
    if re.search(
        r"(?:原定|原计划).{0,30}(?:取消|作废|无需参加)|"
        r"原(?:面试|笔试|测评|考试|会议)?安排.{0,30}(?:取消|作废|无需参加)",
        body,
    ):
        return "cancel"
    if re.search(r"改期|时间调整|时间变更|更新通知", subject):
        return "update"
    return "new"


def _company(subject: str, sender: str) -> str | None:
    bracket = re.search(r"【([^】]{2,30})】", subject)
    if bracket:
        company = normalize(bracket.group(1))
        return {"讯飞招聘": "科大讯飞"}.get(company, company)
    source = re.match(r"来自([^的]{2,30})的", subject)
    if source:
        return normalize(source.group(1))
    acknowledgement = re.search(
        r"感谢(?:您|你)投递([^，。]{2,50}?)(?:校园招聘|校招|招聘|职位|岗位)",
        subject,
    )
    if acknowledgement:
        return normalize(acknowledgement.group(1))
    prefix = re.search(
        r"([\u4e00-\u9fffA-Za-z·.]{2,30}?)(?:20\d{2})?"
        r"(?:校园招聘|校招|招聘|邀请|笔试|测评|面试)",
        subject,
    )
    if prefix:
        company = normalize(prefix.group(1))
        return re.split(r"邀请|邀您|诚邀|通知", company, maxsplit=1)[0]
    sender_name = sender.partition("<")[0].strip()
    return sender_name[:30] if 2 <= len(sender_name) <= 30 else None


def _role(body: str) -> str | None:
    for pattern in ROLE_PATTERNS:
        match = pattern.search(body)
        if match:
            value = normalize(match.group(1))
            value = re.split(
                r"\s*(?:面试时间|笔试时间|测评时间|结果|姓名|候选人|您好|你好)"
                r"\s*[:：，,]?",
                value,
                maxsplit=1,
            )[0]
            value = re.sub(r"^【[^】]{2,30}】\s*", "", value)
            value = redact_text(value).strip(" -—|：:")
            return value[:80] or None
    return None


def _project(text: str) -> str | None:
    match = re.search(r"(20\d{2}届?(?:校园招聘|校招|秋招|春招))", text)
    return match.group(1) if match else None


def _round(text: str) -> str | None:
    for label in ("终面", "一面", "二面", "三面", "四面", "HR面", "HR 面"):
        if label in text:
            return label.replace(" ", "")
    match = re.search(r"第\s*(\d+)\s*轮", text)
    return f"第{match.group(1)}轮" if match else None


def _evidence(text: str) -> tuple[str, ...]:
    sentences = re.split(r"(?<=[。！？!?；;])\s*", text)
    selected: list[str] = []
    for sentence in sentences:
        if any(
            keyword in sentence
            for keyword in (
                "请于",
                "请在",
                "时间",
                "截止",
                "失效",
                "准备",
                "携带",
                "完成",
                "链接",
                "面试",
                "笔试",
                "测评",
                "简历",
            )
        ):
            cleaned = redact_text(sentence)
            cleaned = re.sub(r"https?://\S+", "[本地链接]", cleaned)
            if 8 <= len(cleaned) <= 220 and cleaned not in selected:
                selected.append(cleaned)
        if len(selected) >= 3:
            break
    return tuple(selected)


def parse_record(record: MailRecord) -> ParsedEvent | None:
    subject = normalize(record.subject)
    body = normalize(record.body)
    combined = normalize(f"{subject} {body}")
    matches = tuple(keyword for keyword in RECRUITING_KEYWORDS if keyword.lower() in combined.lower())
    if not matches:
        return None
    stage = _stage(subject, body)
    start, end, deadline = _times(combined, record.received_at.astimezone(SHANGHAI))
    company = _company(subject, record.sender)
    role = _role(record.body)
    requirements = _evidence(record.body)
    source_id = record.message_id or (
        "<generated-"
        + sha256(
            f"{record.sender}|{subject}|{record.received_at.isoformat()}".encode()
        ).hexdigest()
        + ">"
    )
    links = URL_PATTERN.findall(combined)
    confidence = 0.45
    confidence += min(0.2, len(matches) * 0.04)
    confidence += 0.2 if start or deadline else 0
    confidence += 0.08 if company else 0
    confidence += 0.04 if role else 0
    confidence += 0.03 if stage != "招聘通知" else 0
    if stage == "未通过":
        action = "确认招聘结果，并决定是否归档本次申请。"
        requirements = ()
    elif stage == "Offer":
        action = "核对 Offer 内容、回复要求和明确截止时间。"
    else:
        action = requirements[0] if requirements else redact_text(subject)
    return ParsedEvent(
        company=company,
        role=role,
        recruiting_project=_project(combined),
        event_type=_event_type(stage),
        stage=stage,
        round=_round(combined),
        title=redact_text(subject),
        start_at=start,
        end_at=end,
        deadline_at=deadline,
        source_message_id=source_id,
        source_received_at=record.received_at.astimezone(SHANGHAI),
        source_sender=record.sender,
        source_url=links[0] if links else None,
        action_summary=action,
        requirements=requirements,
        matched_keywords=matches,
        confidence=round(min(0.99, confidence), 2),
        change_type=_change(subject, body),  # type: ignore[arg-type]
    )
