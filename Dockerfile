FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first (layer-cached until pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra sqlite

# Copy application source and install the project itself
COPY src/ ./src/
COPY app.py ./
COPY workspace/ ./workspace/
RUN uv sync --frozen --no-dev --extra sqlite

EXPOSE 9001

CMD ["uv", "run", "uvicorn", "app:gw", "--host", "0.0.0.0", "--port", "9001", "--workers", "1"]
