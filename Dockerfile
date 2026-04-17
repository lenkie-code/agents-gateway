FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first (layer-cached until pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra sqlite

# Copy application source
COPY src/ ./src/
COPY app.py ./
COPY workspace/ ./workspace/

EXPOSE 9001

CMD ["uv", "run", "uvicorn", "app:gw", "--host", "0.0.0.0", "--port", "9001", "--workers", "1"]
