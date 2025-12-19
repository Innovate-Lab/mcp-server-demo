from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required
    GEMINI_API_KEY: str = Field(default="", description="API key for Gemini")
    MCP_API_KEY: str = Field(default="sk-1234", description="API key for MCP clients")

    # Server binding
    MCP_HOST: str = Field(default="0.0.0.0", description="Host to bind")
    MCP_PORT: int = Field(default=8000, description="Port to bind")
    MCP_RELOAD: bool = Field(default=False, description="Enable uvicorn reload (dev only)")

    MCP_TRANSPORT: str = Field(default="streamable-http", description="MCP transport")

    MCP_ALLOWED_HOSTS: str = Field(default="localhost:*,127.0.0.1:*")
    MCP_ALLOWED_ORIGINS: str = Field(default="http://localhost:*")

    @property
    def MCP_ALLOWED_HOSTS_LIST(self) -> list[str]:
        return [x.strip() for x in self.MCP_ALLOWED_HOSTS.split(",") if x.strip()]

    @property
    def MCP_ALLOWED_ORIGINS_LIST(self) -> list[str]:
        return [x.strip() for x in self.MCP_ALLOWED_ORIGINS.split(",") if x.strip()]

    # Logs
    LOG_LEVEL: str = Field(default="INFO", description="Log level")

    # Storage
    STATIC_DIR: str = Field(default="static", description="Static folder name")
    STORAGE_BACKEND: str = Field(default="auto", description="Storage backend: auto|local|gcs")
    GCS_BUCKET: str = Field(default="", description="GCS bucket name")
    GCS_PREFIX: str = Field(default="", description="GCS object prefix")
    GCS_PUBLIC_READ: bool = Field(default=True, description="Try to make uploaded objects public")

    # REST
    GEMINI_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Gemini REST base URL",
    )

    GEMINI_IMAGE_MODEL: str = Field(
        default="gemini-2.5-flash-image",
        description="Model id for image generation",
    )
    GEMINI_VISION_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Model id for vision (image analysis/OCR)",
    )
    GEMINI_TTS_MODEL: str = Field(
        default="gemini-2.5-flash-preview-tts",
        description="Model id for text-to-speech",
    )

    HTTP_TIMEOUT_SECONDS: float = Field(default=120.0, description="Outbound HTTP timeout")
    MAX_IMAGE_DOWNLOAD_BYTES: int = Field(
        default=20 * 1024 * 1024,
        description="Max bytes allowed when downloading image_url",
    )

    # Public URL
    BASE_URL: str = Field(default="", description="Public base url")

    # Backward compatibility
    HOST: str | None = None
    PORT: int | None = None
    GOOGLE_API_KEY: str | None = None

    def normalized_transport(self) -> str:
        return (self.MCP_TRANSPORT or "streamable-http").strip().lower().replace("_", "-")


@lru_cache()
def get_settings() -> Settings:
    s = Settings()

    # Backward compatibility
    if s.HOST:
        s.MCP_HOST = s.HOST
    if s.PORT:
        s.MCP_PORT = s.PORT
    if not s.GEMINI_API_KEY and s.GOOGLE_API_KEY:
        s.GEMINI_API_KEY = s.GOOGLE_API_KEY

    # Default URL for local static links
    if not s.BASE_URL:
        host_for_url = "localhost" if s.MCP_HOST in ("0.0.0.0", "::") else s.MCP_HOST
        s.BASE_URL = f"http://{host_for_url}:{s.MCP_PORT}"

    # Ensure local static folder exists if not using GCS
    backend = (s.STORAGE_BACKEND or "auto").strip().lower()
    use_gcs = bool(s.GCS_BUCKET) and backend in ("auto", "gcs")
    if not use_gcs:
        static_path = BASE_DIR / s.STATIC_DIR
        os.makedirs(static_path, exist_ok=True)

    return s


settings = get_settings()