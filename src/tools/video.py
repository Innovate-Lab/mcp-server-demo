from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional, Tuple

import anyio
import httpx

from src.config import settings
from src.storage import save_file_locally

logger = logging.getLogger(__name__)

# Models pool
_FALLBACK_MODELS = [
    "veo-3.0-generate-001",
    "veo-3.0-fast-generate-001",
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.1-generate-preview",
]

_ALLOWED_ASPECT_RATIOS = {"16:9", "9:16"}
_ALLOWED_RESOLUTIONS = {"720p", "1080p"}

_DEFAULT_ASPECT_RATIO = "16:9"
_DEFAULT_RESOLUTION = "720p"

_POLL_INTERVAL_S = 10
_POLL_TIMEOUT_S = 10 * 60  # 10 minutes


def _validate_inputs(
    *,
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    image_url: Optional[str],
    image_base64: Optional[str],
) -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required")

    if aspect_ratio not in _ALLOWED_ASPECT_RATIOS:
        raise ValueError(f"aspect_ratio must be one of {sorted(_ALLOWED_ASPECT_RATIOS)}")

    if resolution not in _ALLOWED_RESOLUTIONS:
        raise ValueError(f"resolution must be one of {sorted(_ALLOWED_RESOLUTIONS)}")

    # Constraint from requirements UI: 1080p only for 16:9; 9:16 only supports 720p.
    if aspect_ratio == "9:16" and resolution != "720p":
        raise ValueError('resolution must be "720p" when aspect_ratio is "9:16"')
    if resolution == "1080p" and aspect_ratio != "16:9":
        raise ValueError('aspect_ratio must be "16:9" when resolution is "1080p"')

    if image_url and image_base64:
        raise ValueError("Provide either image_url or image_base64, not both")


def _normalize_b64(s: str) -> str:
    """Accept raw base64 or data URLs; returns raw base64 content."""
    s = s.strip()
    if s.startswith("data:"):
        parts = s.split(",", 1)
        if len(parts) != 2:
            raise ValueError("image_base64 looks like a data URL but is malformed")
        return parts[1].strip()
    return s


async def _fetch_image_as_b64(url: str) -> Tuple[str, Optional[str]]:
    """
    Downloads image bytes from a public URL and returns (base64, detected_mime_type).
    """
    timeout = httpx.Timeout(30.0, read=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        mime = r.headers.get("content-type")
        b64 = base64.b64encode(r.content).decode("ascii")
        return b64, mime


def _build_request_body(
    *,
    prompt: str,
    negative_prompt: Optional[str],
    aspect_ratio: str,
    resolution: str,
    image_b64: Optional[str],
    image_mime_type: Optional[str],
) -> Dict[str, Any]:
    instance: Dict[str, Any] = {"prompt": prompt}

    if image_b64:
        instance["image"] = {
            "imageBytes": image_b64,
            "mimeType": image_mime_type or "image/jpeg",
        }

    params: Dict[str, Any] = {
        "aspectRatio": aspect_ratio,
        "resolution": resolution,
    }
    if negative_prompt:
        params["negativePrompt"] = negative_prompt

    return {"instances": [instance], "parameters": params}


def _extract_operation_name(resp_json: Dict[str, Any]) -> str:
    name = resp_json.get("name")
    if isinstance(name, str) and name.strip():
        return name
    raise RuntimeError(f"Unexpected Veo response (missing operation name): {resp_json}")


def _extract_video_uri(op_json: Dict[str, Any]) -> str:
    response = op_json.get("response") or {}
    gvr = response.get("generateVideoResponse") or response.get("generate_video_response") or {}
    samples = gvr.get("generatedSamples") or gvr.get("generated_samples") or []
    if isinstance(samples, list) and samples:
        video = samples[0].get("video") if isinstance(samples[0], dict) else None
        if isinstance(video, dict):
            uri = video.get("uri")
            if isinstance(uri, str) and uri.strip():
                return uri

    alt = response.get("generatedVideos") or response.get("generated_videos")
    if isinstance(alt, list) and alt:
        v0 = alt[0]
        if isinstance(v0, dict):
            uri = (v0.get("video") or {}).get("uri")
            if isinstance(uri, str) and uri.strip():
                return uri

    raise RuntimeError(f"Unexpected Veo operation response (missing video uri): {op_json}")


async def _poll_operation(
    client: httpx.AsyncClient,
    *,
    operation_name: str,
    api_key: str,
    timeout_s: int = _POLL_TIMEOUT_S,
) -> Dict[str, Any]:
    deadline = anyio.current_time() + timeout_s
    headers = {"x-goog-api-key": api_key}

    while True:
        r = await client.get(f"/{operation_name}", headers=headers)
        r.raise_for_status()
        data = r.json()

        if data.get("done") is True:
            if isinstance(data.get("error"), dict):
                raise RuntimeError(f"Veo operation failed: {data['error']}")
            return data

        if anyio.current_time() >= deadline:
            raise TimeoutError(f"Veo generation timed out after {timeout_s}s")

        await anyio.sleep(_POLL_INTERVAL_S)


async def _download_video_bytes(
    client: httpx.AsyncClient,
    *,
    video_uri: str,
    api_key: str,
) -> bytes:
    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as dl:
        r = await dl.get(video_uri, headers={"x-goog-api-key": api_key})
        r.raise_for_status()
        return r.content


async def _try_model_once(
    model: str,
    *,
    prompt: str,
    negative_prompt: Optional[str],
    aspect_ratio: str,
    resolution: str,
    image_b64: Optional[str],
    image_mime_type: Optional[str],
) -> Tuple[str, bytes]:
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    base_url = (settings.GEMINI_BASE_URL or "").strip()
    if not base_url:
        raise RuntimeError("GEMINI_BASE_URL is not configured")

    body = _build_request_body(
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        image_b64=image_b64,
        image_mime_type=image_mime_type,
    )

    timeout = httpx.Timeout(30.0, read=60.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        r = await client.post(
            f"/models/{model}:predictLongRunning",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            content=json.dumps(body),
        )
        r.raise_for_status()

        op_name = _extract_operation_name(r.json())
        op_json = await _poll_operation(client, operation_name=op_name, api_key=api_key, timeout_s=_POLL_TIMEOUT_S)
        video_uri = _extract_video_uri(op_json)
        video_bytes = await _download_video_bytes(client, video_uri=video_uri, api_key=api_key)
        return model, video_bytes


async def create_video(
    prompt: str,
    negative_prompt: str | None = None,
    aspect_ratio: str = _DEFAULT_ASPECT_RATIO,
    resolution: str = _DEFAULT_RESOLUTION,
    image_url: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    filename_hint: str | None = None,
) -> Dict[str, Any]:
    _validate_inputs(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        image_url=image_url,
        image_base64=image_base64,
    )

    image_b64: Optional[str] = None
    detected_mime: Optional[str] = None

    if image_url:
        image_b64, detected_mime = await _fetch_image_as_b64(image_url)
    elif image_base64:
        image_b64 = _normalize_b64(image_base64)

    final_image_mime = image_mime_type or detected_mime

    last_error: Optional[Exception] = None
    for model in _FALLBACK_MODELS:
        try:
            used_model, video_bytes = await _try_model_once(
                model,
                prompt=prompt,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                image_b64=image_b64,
                image_mime_type=final_image_mime,
            )
            saved = await save_file_locally(
                video_bytes,
                extension="mp4",
                filename_hint=filename_hint or "video",
                mime_type="video/mp4",
            )
            return {
                "prompt": prompt,
                "model": used_model,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "mime_type": "video/mp4",
                "url": saved["url"],
                "gs_uri": saved.get("gs_uri", ""),
            }
        except Exception as e:
            last_error = e
            logger.warning("Veo model failed; trying next. model=%s error=%s", model, type(e).__name__)

    raise RuntimeError(f"All Veo models failed. Last error: {last_error}")
