FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    HF_HOME=/models

# Same shared dependencies as the API (db, storage, redis, config...)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

# Worker-only: PyTorch (CPU build, much smaller than the GPU one) + OpenCLIP.
# Kept out of pyproject.toml so the API image stays small.
RUN uv pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && uv pip install open_clip_torch

# Code: worker needs the shared api/app modules too
COPY api /app/api
COPY worker /app/worker

CMD ["python", "-m", "worker.worker"]
