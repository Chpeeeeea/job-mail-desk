from __future__ import annotations

import base64
import io

from PIL import Image

from job_mail_desk.image_store import NoteImageStore
from job_mail_desk.paper_store import PaperStore
from job_mail_desk.preferences import load_preferences, update_preferences


def test_paper_markdown_round_trip_backup_and_recoverable_trash(tmp_path):
    store = PaperStore(
        tmp_path / "papers",
        tmp_path / "backups",
        tmp_path / "trash",
    )
    paper = store.create("todo", title="今日准备")
    assert store.path_for(paper.id).read_text(encoding="utf-8").startswith("---\n")

    updated = store.update(
        paper.id,
        title="百度笔试准备",
        body="- [x] 核对时间 <!-- item:done -->\n- [ ] 调试设备 <!-- item:next -->",
        linked_task_ids=["application-baidu"],
    )
    assert updated.title == "百度笔试准备"
    assert "调试设备" in store.load(paper.id).body
    assert (tmp_path / "backups" / f"{paper.id}.md").exists()

    trashed = store.move_to_trash(paper.id)
    assert trashed.exists()
    assert not store.path_for(paper.id).exists()


def test_preferences_are_bounded_and_invalid_values_fall_back(tmp_path):
    path = tmp_path / "preferences.json"
    preferences = update_preferences(
        path,
        {
            "scale": 999,
            "theme": "unknown",
            "markdown_level": "everything",
            "language": "xx",
            "auto_snap_capsules": False,
        },
    )
    assert preferences.scale == 120
    assert preferences.theme == "warm"
    assert preferences.markdown_level == "balanced"
    assert preferences.language == "zh-CN"
    assert load_preferences(path).auto_snap_capsules is False


def test_local_note_image_round_trip(tmp_path):
    image = Image.new("RGB", (12, 8), "#d56c4e")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    source = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    store = NoteImageStore(tmp_path / "assets")
    reference = store.save_data_url(source)
    assert reference.startswith("i:")
    restored = store.data_url(reference)
    assert restored is not None
    assert restored.startswith("data:image/webp;base64,")
    assert store.data_url("i:../../secret.txt") is None
