from __future__ import annotations

from src.storage import save_file_locally


_MIN_MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomiso2"


async def create_video(
    prompt: str,
    negative_prompt: str | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    image_url: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    filename_hint: str | None = None,
) -> dict:

    model = "veo-3.0-generate-001"
    saved = await save_file_locally(_MIN_MP4, extension="mp4", filename_hint=filename_hint or "video")

    return {
        "prompt": prompt,
        "model": model,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "negative_prompt": negative_prompt,
        "mime_type": "video/mp4",
        "url": saved["url"],
        "gs_uri": saved.get("gs_uri", ""),
        "input_image": image_url or ("<base64>" if image_base64 else None),
        "input_image_mime_type": image_mime_type,
    }