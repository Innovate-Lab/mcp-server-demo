from __future__ import annotations

import base64
import json
import socket
from ipaddress import ip_address
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

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
        raise ValueError(f"Invalid aspect_ratio '{value}'. Allowed: {sorted(_ALLOWED_ASPECT_RATIOS)}")
    return v


def _normalize_image_size(value: str) -> str:
    v = (value or "2K").strip().upper()
    if v not in _ALLOWED_IMAGE_SIZES:
        raise ValueError(f"Invalid image_size '{value}'. Allowed: {sorted(_ALLOWED_IMAGE_SIZES)}")
    return v


def _gemini_endpoint(model: str) -> str:
    base = (settings.GEMINI_BASE_URL or "").rstrip("/")
    return f"{base}/models/{model}:generateContent"


def _gemini_headers() -> dict:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return {
        "x-goog-api-key": settings.GEMINI_API_KEY,
        "content-type": "application/json",
    }


def _extract_first_inline_image(data: Dict[str, Any]) -> Tuple[bytes, str]:
    candidates = data.get("candidates") or []
    for cand in candidates:
        content = (cand or {}).get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue

            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict):
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                b64 = inline.get("data")
                if b64:
                    return base64.b64decode(b64), mime

            # Some responses might place 'data' at the part level
            if part.get("data") and (part.get("mimeType") or part.get("mime_type")):
                mime = part.get("mimeType") or part.get("mime_type") or "image/png"
                return base64.b64decode(part["data"]), mime

    raise RuntimeError("Gemini response did not include inline image data: " + json.dumps(data)[:2000])


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


def _is_public_hostname(hostname: str) -> bool:
    if not hostname:
        return False

    # Common localhost names
    hn = hostname.strip().lower()
    if hn in {"localhost", "localhost.localdomain"}:
        return False

    try:
        # Resolve DNS to IPs
        infos = socket.getaddrinfo(hostname, None)
        ips = {info[4][0] for info in infos if info and info[4]}
    except Exception:
        return False

    for ip_str in ips:
        try:
            ip = ip_address(ip_str)
        except Exception:
            return False

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    return True


def _validate_public_http_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in {"http", "https"}:
        raise ValueError("image_url must use http/https")
    if not u.hostname:
        raise ValueError("image_url is invalid")
    if not _is_public_hostname(u.hostname):
        raise ValueError("image_url host is not public-accessible")


async def create_visualization(
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "2K",
    filename_hint: str | None = None,
) -> dict:
    ar = _normalize_aspect_ratio(aspect_ratio)
    size = _normalize_image_size(image_size)

    model = (settings.GEMINI_IMAGE_MODEL or "").strip()
    if not model:
        raise RuntimeError("GEMINI_IMAGE_MODEL is not configured")

    size_hint = {
        "1K": "around 1024px on the long edge",
        "2K": "around 2048px on the long edge",
        "4K": "around 4096px on the long edge",
    }.get(size, size)

    full_prompt = (
        f"{(prompt or '').strip()}\n\n"
        f"Constraints:\n"
        f"- Output: a single PNG image\n"
        f"- Aspect ratio: {ar}\n"
        f"- Target size: {size} ({size_hint})\n"
        f"- Do not add any text or watermark unless explicitly requested\n"
    )

    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "responseModalities": ["Image"],
            "imageConfig": {
                "aspectRatio": ar,
                **({"imageSize": size} if "gemini-3" in model or "3-pro" in model else {}),
            },
        },
    }

    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(_gemini_endpoint(model), headers=_gemini_headers(), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini image generation failed: {resp.status_code} {resp.text[:2000]}")
        data = resp.json()

    image_bytes, mime_type = _extract_first_inline_image(data)
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
    if not image_url and not image_base64:
        raise ValueError("Provide image_url or image_base64")

    model = (settings.GEMINI_VISION_MODEL or "").strip()
    if not model:
        raise RuntimeError("GEMINI_VISION_MODEL is not configured")

    img_bytes: bytes
    img_mime: str = (mime_type or "image/jpeg").strip()

    if image_url:
        _validate_public_http_url(image_url)
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            r = await client.get(image_url)
            r.raise_for_status()
            content = r.content
            if len(content) > settings.MAX_IMAGE_DOWNLOAD_BYTES:
                raise ValueError(
                    f"image_url is too large: {len(content)} bytes (max {settings.MAX_IMAGE_DOWNLOAD_BYTES})"
                )
            img_bytes = content
            ct = (r.headers.get("content-type") or "").split(";")[0].strip()
            if ct:
                img_mime = ct
    else:
        b64 = (image_base64 or "").strip()
        if b64.startswith("data:") and "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise ValueError("image_base64 is not valid base64") from e

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        # REST JSON uses camelCase for inlineData/mimeType.
                        "inlineData": {
                            "mimeType": img_mime,
                            "data": base64.b64encode(img_bytes).decode("utf-8"),
                        }
                    },
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(_gemini_endpoint(model), headers=_gemini_headers(), json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Gemini vision failed: {resp.status_code} {resp.text[:2000]}")
        data = resp.json()

    analysis_text = _extract_text(data)
    return {
        "prompt": prompt,
        "analysis": analysis_text,
        "image_url": image_url or "<base64>",
    }