from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Tuple

import httpx

from src.config import settings
from src.storage import save_file_locally


_ALLOWED_ASPECT_RATIOS = {
    # Square
    "1:1",
    # Landscape
    "21:9",
    "16:9",
    "4:3",
    "3:2",
    # Portrait
    "9:16",
    "3:4",
    "2:3",
    # Flexible
    "5:4",
    "4:5",
}

_ALLOWED_IMAGE_SIZES = {"1K", "2K", "4K"}


def _normalize_aspect_ratio(value: str) -> str:
    v = (value or "1:1").strip()
    if v not in _ALLOWED_ASPECT_RATIOS:
        raise ValueError(
            f"Invalid aspect_ratio '{value}'. Allowed: {sorted(_ALLOWED_ASPECT_RATIOS)}"
        )
    return v


def _normalize_image_size(value: str) -> str:
    v = (value or "2K").strip().upper()
    if v not in _ALLOWED_IMAGE_SIZES:
        raise ValueError(f"Invalid image_size '{value}'. Allowed: {sorted(_ALLOWED_IMAGE_SIZES)}")
    return v


def _build_image_prompt(prompt: str, aspect_ratio: str, image_size: str) -> str:
    # We keep this as text constraints to avoid relying on vendor-specific JSON fields that may change.
    size_hint = {
        "1K": "around 1024px on the long edge",
        "2K": "around 2048px on the long edge",
        "4K": "around 4096px on the long edge",
    }.get(image_size, image_size)

    return (
        f"{prompt.strip()}\n\n"
        f"Constraints:\n"
        f"- Output: a single PNG image\n"
        f"- Aspect ratio: {aspect_ratio}\n"
        f"- Target size: {image_size} ({size_hint})\n"
        f"- Do not add any text or watermark unless explicitly requested\n"
    )


def _gemini_url(model: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    base = (settings.GEMINI_BASE_URL or "").rstrip("/")
    return f"{base}/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"


def _extract_first_image(data: Dict[str, Any]) -> Tuple[bytes, str]:
    """Return (image_bytes, mime_type)."""
    candidates = data.get("candidates") or []
    for cand in candidates:
        content = (cand or {}).get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue

            inline = part.get("inlineData") or part.get("inline_data") or part.get("inline_data")
            if isinstance(inline, dict):
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                b64 = inline.get("data")
                if b64:
                    return base64.b64decode(b64), mime

            # Some responses might place 'data' at the part level
            if part.get("data") and (part.get("mimeType") or part.get("mime_type")):
                mime = part.get("mimeType") or part.get("mime_type") or "image/png"
                return base64.b64decode(part["data"]), mime

    raise RuntimeError(
        "Gemini response did not include inline image data. " + json.dumps(data)[:2000]
    )


def _extract_text(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return json.dumps(data)[:2000]

    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "\n".join(chunks).strip() or json.dumps(data)[:2000]


async def create_visualization(
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "2K",
    filename_hint: str | None = None,
) -> dict:
    """Create an image from text prompt using Gemini, upload it, and return public URL."""
    ar = _normalize_aspect_ratio(aspect_ratio)
    size = _normalize_image_size(image_size)

    model = (settings.GEMINI_IMAGE_MODEL or "").strip()
    if not model:
        raise RuntimeError("GEMINI_IMAGE_MODEL is not configured")

    full_prompt = _build_image_prompt(prompt, ar, size)

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}],
            }
        ],
        "generationConfig": {
            # This is a stable field; if supported, it encourages PNG output.
            "responseMimeType": "image/png"
        },
    }

    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(_gemini_url(model), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Gemini image generation failed: {resp.status_code} {resp.text[:2000]}"
            )
        data = resp.json()

    image_bytes, mime_type = _extract_first_image(data)
    extension = "png" if (mime_type or "").endswith("png") else "bin"
    saved = await save_file_locally(
        image_bytes,
        extension=extension,
        filename_hint=filename_hint or "image",
        mime_type=mime_type,
    )

    return {
        "prompt": prompt,
        "aspect_ratio": ar,
        "image_size": size,
        "mime_type": mime_type or "image/png",
        "url": saved["url"],
        "gs_uri": saved.get("gs_uri", ""),
    }


async def analyze_image(
    image_url: str | None = None,
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
    prompt: str = "Describe this image in detail.",
) -> dict:
    """Analyze an image using Gemini Vision.

    Provide either image_url (must be publicly accessible) or image_base64.
    """
    if not image_url and not image_base64:
        raise ValueError("Provide image_url or image_base64")

    model = (settings.GEMINI_VISION_MODEL or "").strip()
    if not model:
        raise RuntimeError("GEMINI_VISION_MODEL is not configured")

    img_bytes: bytes
    img_mime: str = (mime_type or "image/jpeg").strip()

    if image_url:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS, follow_redirects=True) as client:
            r = await client.get(image_url)
            r.raise_for_status()
            content = r.content
            if len(content) > settings.MAX_IMAGE_DOWNLOAD_BYTES:
                raise ValueError(
                    f"image_url is too large: {len(content)} bytes (max {settings.MAX_IMAGE_DOWNLOAD_BYTES})"
                )
            img_bytes = content
            # Prefer server-provided content type if present
            ct = (r.headers.get("content-type") or "").split(";")[0].strip()
            if ct:
                img_mime = ct
    else:
        try:
            img_bytes = base64.b64decode(image_base64 or "", validate=True)
        except Exception:
            # Some clients send data URLs. Try to strip header.
            b64 = (image_base64 or "").strip()
            if b64.startswith("data:") and "," in b64:
                b64 = b64.split(",", 1)[1]
            img_bytes = base64.b64decode(b64)

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": img_mime,
                            "data": base64.b64encode(img_bytes).decode("utf-8"),
                        }
                    },
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(_gemini_url(model), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini vision failed: {resp.status_code} {resp.text[:2000]}")
        data = resp.json()

    analysis_text = _extract_text(data)
    return {
        "prompt": prompt,
        "analysis": analysis_text,
        "image_url": image_url or "<base64>",
    }
