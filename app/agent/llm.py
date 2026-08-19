from __future__ import annotations

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.config import settings


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOllama:
    # temperature=0: routing/tool-calling/critique are classification-like
    # decisions, not creative generation - deterministic-ish output is what
    # we actually want for every node except the final answer synthesis,
    # and there's no strong reason to vary it there either for a support bot.
    return ChatOllama(
        model=settings.ollama_chat_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )
