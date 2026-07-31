from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from .markdown_store import _atomic_write


PaperKind = Literal["todo", "note"]
THEMES = {"system", "warm", "ink", "forest", "sunset"}


@dataclass
class Paper:
    id: str
    kind: PaperKind
    title: str
    body: str
    theme: str = "warm"
    linked_task_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "theme": self.theme,
            "linked_task_ids": self.linked_task_ids,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.metadata()
        payload["body"] = self.body
        return payload


def render_paper(paper: Paper) -> str:
    frontmatter = yaml.safe_dump(
        paper.metadata(),
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n{paper.body.rstrip()}\n"


def parse_paper(path: Path) -> Paper:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"纸片缺少 frontmatter：{path}")
    _, frontmatter, body = content.split("---", maxsplit=2)
    payload = yaml.safe_load(frontmatter) or {}
    kind = str(payload.get("kind") or "note")
    if kind not in {"todo", "note"}:
        raise ValueError(f"无效纸片类型：{kind}")

    def parse_time(name: str) -> datetime:
        value = payload.get(name)
        return (
            datetime.fromisoformat(str(value))
            if value
            else datetime.now().astimezone()
        )

    return Paper(
        id=str(payload["id"]),
        kind=kind,  # type: ignore[arg-type]
        title=str(payload.get("title") or "未命名纸片"),
        body=body.lstrip("\r\n").rstrip(),
        theme=str(payload.get("theme") or "warm"),
        linked_task_ids=list(payload.get("linked_task_ids") or []),
        created_at=parse_time("created_at"),
        updated_at=parse_time("updated_at"),
    )


class PaperStore:
    def __init__(
        self,
        papers_dir: Path,
        backups_dir: Path,
        trash_dir: Path,
    ) -> None:
        self.papers_dir = papers_dir
        self.backups_dir = backups_dir
        self.trash_dir = trash_dir
        for path in (papers_dir, backups_dir, trash_dir):
            path.mkdir(parents=True, exist_ok=True)

    def path_for(self, paper_id: str) -> Path:
        return self.papers_dir / f"{paper_id}.md"

    def create(
        self,
        kind: PaperKind,
        *,
        title: str | None = None,
        theme: str = "warm",
    ) -> Paper:
        if kind not in {"todo", "note"}:
            raise ValueError("纸片类型必须是 todo 或 note")
        paper = Paper(
            id=uuid.uuid4().hex[:20],
            kind=kind,
            title=(title or ("新待办纸" if kind == "todo" else "新笔记纸"))[:80],
            body="- [ ] 新待办" if kind == "todo" else "# 新笔记\n\n开始记录……",
            theme=theme if theme in THEMES else "warm",
        )
        self.save(paper)
        return paper

    def save(self, paper: Paper) -> Path:
        if paper.theme not in THEMES:
            paper.theme = "warm"
        paper.updated_at = datetime.now().astimezone()
        path = self.path_for(paper.id)
        if path.exists():
            backup = self.backups_dir / f"{paper.id}.md"
            shutil.copy2(path, backup)
        _atomic_write(path, render_paper(paper))
        return path

    def load(self, paper_id: str) -> Paper | None:
        path = self.path_for(paper_id)
        return parse_paper(path) if path.exists() else None

    def all(self) -> list[Paper]:
        papers: list[Paper] = []
        for path in sorted(self.papers_dir.glob("*.md")):
            try:
                papers.append(parse_paper(path))
            except (KeyError, TypeError, ValueError, yaml.YAMLError):
                continue
        return sorted(papers, key=lambda item: item.updated_at, reverse=True)

    def update(
        self,
        paper_id: str,
        *,
        body: str,
        title: str | None = None,
        theme: str | None = None,
        linked_task_ids: list[str] | None = None,
    ) -> Paper:
        paper = self.load(paper_id)
        if not paper:
            raise KeyError(paper_id)
        if len(body.encode("utf-8")) > 1_000_000:
            raise ValueError("单张纸片不能超过 1 MB")
        paper.body = body
        if title is not None:
            paper.title = title.strip()[:80] or "未命名纸片"
        if theme is not None:
            paper.theme = theme if theme in THEMES else paper.theme
        if linked_task_ids is not None:
            paper.linked_task_ids = linked_task_ids[:100]
        self.save(paper)
        return paper

    def move_to_trash(self, paper_id: str) -> Path:
        path = self.path_for(paper_id)
        if not path.exists():
            raise KeyError(paper_id)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.trash_dir / f"{paper_id}-{stamp}.md"
        shutil.move(path, target)
        return target

