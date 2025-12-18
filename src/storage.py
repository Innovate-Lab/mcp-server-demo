from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiofiles
import anyio

from src.config import BASE_DIR, settings

try:
    from google.cloud import storage as gcs_storage  # type: ignore
except Exception:  # pragma: no cover
    gcs_storage = None  # type: ignore


def _safe_filename(name: str) -> str:
    name = (name or "file").strip()
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    name = name.strip("._-") or "file"
    return name


def _make_filename(extension: str, filename_hint: Optional[str]) -> str:
    ext = (extension or "bin").lstrip(".")
    hint = _safe_filename(filename_hint or "file")
    unique = uuid.uuid4().hex[:12]
    return f"{unique}_{hint}.{ext}"


@dataclass(frozen=True)
class SaveResult:
    url: str
    gs_uri: str = ""


async def _save_local(data: bytes, *, extension: str, filename_hint: str | None = None) -> SaveResult:
    filename = _make_filename(extension, filename_hint)
    static_path = Path(BASE_DIR) / settings.STATIC_DIR
    file_path = static_path / filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(data)

    url = f"{settings.BASE_URL}/static/{filename}"
    return SaveResult(url=url, gs_uri="")


def _gcs_object_name(filename: str) -> str:
    prefix = (settings.GCS_PREFIX or "").strip().strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def _upload_gcs_sync(data: bytes, *, object_name: str, content_type: str | None) -> SaveResult:
    if gcs_storage is None:
        raise RuntimeError("google-cloud-storage is not available")

    bucket_name = (settings.GCS_BUCKET or "").strip()
    if not bucket_name:
        raise RuntimeError("GCS_BUCKET is not configured")

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    blob.upload_from_string(data, content_type=content_type)

    if settings.GCS_PUBLIC_READ:
        # NOTE: If your bucket uses Uniform bucket-level access, make_public() may be blocked.
        # In that case, you should configure public access at the bucket/policy level.
        try:
            blob.make_public()
        except Exception:
            # Still return URLs; access might be controlled by bucket policy.
            pass

    url = f"https://storage.googleapis.com/{bucket_name}/{object_name}"
    gs_uri = f"gs://{bucket_name}/{object_name}"
    return SaveResult(url=url, gs_uri=gs_uri)


async def _save_gcs(data: bytes, *, extension: str, filename_hint: str | None = None, mime_type: str | None = None) -> SaveResult:
    filename = _make_filename(extension, filename_hint)
    object_name = _gcs_object_name(filename)
    return await anyio.to_thread.run_sync(_upload_gcs_sync, data, object_name=object_name, content_type=mime_type)


def _should_use_gcs() -> bool:
    backend = (settings.STORAGE_BACKEND or "auto").strip().lower()
    if backend == "local":
        return False
    if backend == "gcs":
        return True
    # auto
    return bool(settings.GCS_BUCKET)


async def save_file(
    data: bytes,
    extension: str,
    filename_hint: str | None = None,
    mime_type: str | None = None,
) -> dict:
    """Save bytes and return public URL + optional gs:// URI.

    Backend is controlled by env:
      - STORAGE_BACKEND=local|gcs|auto
      - GCS_BUCKET, GCS_PREFIX, GCS_PUBLIC_READ
    """

    if _should_use_gcs():
        res = await _save_gcs(data, extension=extension, filename_hint=filename_hint, mime_type=mime_type)
    else:
        res = await _save_local(data, extension=extension, filename_hint=filename_hint)

    return {"url": res.url, "gs_uri": res.gs_uri}


# Backward-compatible name used by existing tools
async def save_file_locally(
    data: bytes,
    extension: str,
    filename_hint: str | None = None,
    mime_type: str | None = None,
) -> dict:
    return await save_file(data, extension=extension, filename_hint=filename_hint, mime_type=mime_type)
