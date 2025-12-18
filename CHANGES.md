# Changes implemented

This update implements:

- Tool 1: `create_visualization` (Gemini image generation -> upload -> public URL)
- Tool 3: `analyze_image` (Gemini vision analysis / OCR)

## Files changed

### `src/tools/image.py`
- Replaced placeholder 1px PNG generation with real Gemini call (`models/{GEMINI_IMAGE_MODEL}:generateContent`).
- Added strict validation for `aspect_ratio` and `image_size`.
- Implemented `analyze_image`:
  - Accepts `image_url` (downloads it) or `image_base64`
  - Sends image inline to Gemini vision model (`GEMINI_VISION_MODEL`)
  - Returns analysis text from Gemini response.

### `src/storage.py`
- Added storage backend selection:
  - `STORAGE_BACKEND=local|gcs|auto`
  - If GCS is enabled, uploads to `GCS_BUCKET` (optional `GCS_PREFIX`) and returns
    `https://storage.googleapis.com/...` + `gs://...`
  - Otherwise saves to local `/static` and returns `BASE_URL/static/...`
- Kept backward compatible function name `save_file_locally()` so existing tools still work.

### `src/config.py`
- Added configuration options:
  - Storage: `STORAGE_BACKEND`, `GCS_BUCKET`, `GCS_PREFIX`, `GCS_PUBLIC_READ`
  - Gemini: `GEMINI_BASE_URL`, `GEMINI_IMAGE_MODEL`, `GEMINI_VISION_MODEL`
  - Limits/timeouts: `MAX_IMAGE_DOWNLOAD_BYTES`, `HTTP_TIMEOUT_SECONDS`
- Only creates local `STATIC_DIR` folder when local storage is used.

### `src/auth.py`
- Allows `OPTIONS` requests to pass through without requiring `x-api-key` (CORS preflight).

### `README.md`
- Added basic setup and environment documentation.

## Session Management note (streamable-http)
The MCP library handles session management. When using streamable-http:
- Client calls `initialize` first, server returns session id.
- Subsequent POST /mcp calls must include `mcp-session-id` header.
