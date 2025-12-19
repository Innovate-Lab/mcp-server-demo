# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY --from=ghcr.io/astral-sh/uv:0.5.20 /uv /usr/local/bin/uv

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app --uid 10001 app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --compile-bytecode

COPY src/ ./src/

RUN mkdir -p /app/static && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "src.main"]
