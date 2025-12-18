FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache
COPY src/ ./src/
COPY .env .env 
EXPOSE 8000
CMD ["uv", "run", "mcp", "run", "src/main.py", "--transport", "sse", "--port", "8000", "--host", "0.0.0.0"]