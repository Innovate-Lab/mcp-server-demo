from __future__ import annotations

import re
import uuid
from pathlib import Path

import aiofiles

from src.config import BASE_DIR, settings


def _safe_filename(name: str) -> str:
    name = (name or "file").strip()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.strip("._-") or "file"
    return name


async def save_file_locally(
    data: bytes,
    extension: str,
    filename_hint: str | None = None,
) -> dict:

    ext = (extension or "bin").lstrip(".")
    hint = _safe_filename(filename_hint or "file")
    unique = uuid.uuid4().hex[:12]
    filename = f"{unique}_{hint}.{ext}"

    static_path = Path(BASE_DIR) / settings.STATIC_DIR
    file_path = static_path / filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(data)

    url = f"{settings.BASE_URL}/static/{filename}"
    return {"url": url, "gs_uri": ""}
