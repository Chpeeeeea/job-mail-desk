from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from PIL import Image


MAX_IMAGE_BYTES = 8_000_000
MAX_EDGE = 2400


class NoteImageStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def save_data_url(self, value: str) -> str:
        header, separator, payload = value.partition(",")
        if not separator or not header.startswith("data:image/"):
            raise ValueError("仅支持图片 data URL")
        raw = base64.b64decode(payload, validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能超过 8 MB")
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            image.thumbnail((MAX_EDGE, MAX_EDGE))
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            output = io.BytesIO()
            if image.mode == "RGBA":
                image.save(output, format="PNG", optimize=True)
                extension = "png"
                mime = "image/png"
            else:
                image.save(output, format="WEBP", quality=88, method=6)
                extension = "webp"
                mime = "image/webp"
        optimized = output.getvalue()
        digest = hashlib.sha256(optimized).hexdigest()[:24]
        path = self.root / f"{digest}.{extension}"
        if not path.exists():
            path.write_bytes(optimized)
        return f"i:{path.name}"

    def data_url(self, reference: str) -> str | None:
        if not reference.startswith("i:"):
            return None
        name = Path(reference[2:]).name
        path = self.root / name
        if not path.exists():
            return None
        mime = "image/png" if path.suffix.lower() == ".png" else "image/webp"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

