# mcp-server-demo

Demo MCP server (FastMCP) exposing tools for:
- create_visualization (Gemini image generation -> upload -> URL)
- analyze_image (Gemini vision analysis / OCR)
- text_to_speech (placeholder WAV generator)
- create_video (placeholder MP4 generator)

## Environment

Required:
- `GEMINI_API_KEY` - Gemini API key
- `MCP_API_KEY` - API key required via `x-api-key` header (except `/health`)

Optional (storage):
- `STORAGE_BACKEND` = `auto` (default) | `local` | `gcs`
- `GCS_BUCKET` - if set (and backend is `auto`/`gcs`), uploads go to GCS
- `GCS_PREFIX` - object prefix/folder in the bucket
- `GCS_PUBLIC_READ` - default `true`

## Run (dev)

```bash
uv sync
uv run python -m src.main
```

Health check:
```bash
curl http://localhost:8000/health
```
