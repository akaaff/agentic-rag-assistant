"""Langfuse tracing (infra/docker-compose.langfuse.yml, self-hosted).

Deliberately optional: get_langfuse_handler() returns None when the
LANGFUSE_* settings aren't configured, so this app runs identically
without the (heavy - Postgres+ClickHouse+Redis+MinIO+2 containers) tracing
stack running. Verified live: a real qwen2.5:7b-instruct call through
ChatOllama, routed through this handler, showed up in Langfuse's own web
UI with full input/output/latency/cost detail within seconds.
"""

from __future__ import annotations

from functools import lru_cache

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config import settings


@lru_cache(maxsize=1)
def get_langfuse_handler() -> CallbackHandler | None:
    has_host = bool(settings.langfuse_host)
    has_keys = bool(settings.langfuse_public_key) and bool(settings.langfuse_secret_key)
    if not (has_host and has_keys):
        return None
    # Langfuse's SDK v4 (OTel-based) registers the client globally on
    # construction; CallbackHandler then looks it up by public_key rather
    # than taking full credentials itself - verified this exact two-step
    # pattern live before wiring it into the app.
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return CallbackHandler(public_key=settings.langfuse_public_key)
