from __future__ import annotations

import base64

from src.storage import save_file_locally


_ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+Zg9kAAAAASUVORK5CYII="
)


async def create_visualization(
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "2K",
    filename_hint: str | None = None,
) -> dict:

    image_bytes = base64.b64decode(_ONE_PIXEL_PNG_BASE64)
    saved = await save_file_locally(image_bytes, extension="png", filename_hint=filename_hint or "image")

    return {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "mime_type": "image/png",
        "url": saved["url"],
        "gs_uri": saved.get("gs_uri", ""),
    }


async def analyze_image(
    image_url: str | None = None,
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
    prompt: str = "Describe this image in detail.",
) -> dict:

    if not image_url and not image_base64:
        raise ValueError("Provide image_url or image_base64")

    source = image_url or "<base64>"
    analysis = "Not implemented yet. This is a placeholder response for core testing."

    return {
        "prompt": prompt,
        "analysis": analysis,
        "image_url": source,
        "mime_type": mime_type,
    }
