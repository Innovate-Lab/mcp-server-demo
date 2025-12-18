from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings


def verify_api_key(headers) -> None:

    required_key = settings.MCP_API_KEY
    if not required_key:
        return 

    provided = headers.get("x-api-key")
    if not provided:
        raise PermissionError("missing")
    if provided != required_key:
        raise PermissionError("invalid")


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or ""
        if path == "/health" or path.startswith("/static"):
            return await call_next(request)

        try:
            verify_api_key(request.headers)
        except PermissionError as e:
            if str(e) == "missing":
                return JSONResponse({"error": "Missing x-api-key header"}, status_code=401)
            return JSONResponse({"error": "Invalid API key"}, status_code=403)

        return await call_next(request)
