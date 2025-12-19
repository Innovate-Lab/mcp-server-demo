from __future__ import annotations

import logging
import uvicorn

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from mcp.server.fastmcp import FastMCP

from src.auth import ApiKeyAuthMiddleware
from src.config import BASE_DIR, settings
from src.tools import audio, image, video

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=settings.LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    "mcp-server-demo",
    stateless_http=False,
)

@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(_request):
    return JSONResponse({"status": "ok"})

@mcp.tool()
async def create_visualization(
    prompt: str,
    aspect_ratio: str = "1:1",
    image_size: str = "2K",
    filename_hint: str | None = None,
) -> dict:
    return await image.create_visualization(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        filename_hint=filename_hint,
    )

@mcp.tool()
async def text_to_speech(
    prompt: str,
    voice_name: str = "Kore",
    multi_speaker_config: str | list[dict] | None = None,
    filename_hint: str | None = None,
) -> dict:
    return await audio.text_to_speech(
        prompt=prompt,
        voice_name=voice_name,
        multi_speaker_config=multi_speaker_config,
        filename_hint=filename_hint,
    )

@mcp.tool()
async def analyze_image(
    image_url: str | None = None,
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
    prompt: str = "Describe this image in detail.",
) -> dict:
    return await image.analyze_image(
        image_url=image_url,
        image_base64=image_base64,
        mime_type=mime_type,
        prompt=prompt,
    )

@mcp.tool()
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
    return await video.create_video(
        prompt=prompt,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        image_url=image_url,
        image_base64=image_base64,
        image_mime_type=image_mime_type,
        filename_hint=filename_hint,
    )

def build_app():
    transport = settings.normalized_transport()
    static_dir = str((BASE_DIR / settings.STATIC_DIR).resolve())

    # streamable-http: POST /mcp
    # sse: GET /sse + POST /messages/
    if transport == "sse":
        app = mcp.sse_app()
        logger.info("MCP transport: sse (GET /sse, POST /messages/)")
    else:
        app = mcp.streamable_http_app()
        logger.info("MCP transport: streamable-http (POST /mcp)")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id", "mcp-session-id"],
    )
    return app

app = build_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=True,
    )