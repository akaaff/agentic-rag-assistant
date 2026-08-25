# syntax=docker/dockerfile:1

# Multi-stage: dependency install (uv sync, layer-cached on
# pyproject.toml/uv.lock alone) separate from the app code copy, so an
# app-code-only change doesn't re-trigger a from-scratch reinstall of
# torch/sentence-transformers/langgraph - by far the slowest part of this
# build.
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

FROM python:3.13-slim AS runtime

WORKDIR /app

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface

# Non-root, same reasoning as the sibling repo's own Dockerfile - no
# reason this process needs root inside the container. HF_HOME above
# matters together with --no-create-home: verified live that without it,
# sentence-transformers' first-use download of the reranker model
# (rerank.py, triggered from inside retrieve_node on the first real
# request) fails with PermissionError trying to create ~/.cache under
# /home/app, which doesn't exist for a --no-create-home user. Pointing
# HF_HOME at a path under /app instead works because the chown below
# already makes /app itself writable by this user.
RUN groupadd --system app && useradd --system --gid app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Plain `uvicorn app.main:app` here, not the app/main.py __main__ block's
# manual-event-loop workaround - that workaround exists specifically for
# uvicorn.run() forcing ProactorEventLoop on Windows local dev, which
# doesn't exist on this Linux base image at all.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
