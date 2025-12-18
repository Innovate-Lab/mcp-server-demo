from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Config
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    GEMINI_API_KEY: str = Field(default="", description="API key for Gemini")
    MCP_API_KEY: str = Field(default="sk-1234", description="API key for MCP")

    # Server binding
    MCP_HOST: str = Field(default="0.0.0.0", description="Host to bind")
    MCP_PORT: int = Field(default=8000, description="Port to bind")
    MCP_TRANSPORT: str = Field(default="streamable-http", description="MCP transport")

    # Logs
    LOG_LEVEL: str = Field(default="INFO", description="Log level")

    # Storage
    STATIC_DIR: str = Field(default="static", description="Static folder name")

    # Public URL
    BASE_URL: str = Field(default="", description="Public base url")

    # Backward
    HOST: str | None = None
    PORT: int | None = None
    GOOGLE_API_KEY: str | None = None

    def normalized_transport(self) -> str:
        return (self.MCP_TRANSPORT or "streamable-http").strip().lower().replace("_", "-")


@lru_cache()
def get_settings() -> Settings:
    s = Settings()

    # Backward
    if s.HOST:
        s.MCP_HOST = s.HOST
    if s.PORT:
        s.MCP_PORT = s.PORT
    if not s.GEMINI_API_KEY and s.GOOGLE_API_KEY:
        s.GEMINI_API_KEY = s.GOOGLE_API_KEY

    # Default URL
    if not s.BASE_URL:
        host_for_url = "localhost" if s.MCP_HOST in ("0.0.0.0", "::") else s.MCP_HOST
        s.BASE_URL = f"http://{host_for_url}:{s.MCP_PORT}"

    # Ensure exists
    static_path = BASE_DIR / s.STATIC_DIR
    os.makedirs(static_path, exist_ok=True)

    return s


settings = get_settings()