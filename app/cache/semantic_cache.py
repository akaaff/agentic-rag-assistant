from __future__ import annotations

import json
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

GLOBAL_NAMESPACE = "global"


class _RedisLike(Protocol):
    """Structural type for the only two Redis operations this module
    actually uses - lets tests pass a trivial in-memory fake instead of
    the real redis.asyncio.Redis (or a subclass/mock of it) without a
    type: ignore on every call, since the fake only needs to satisfy this
    narrow shape, not the full client's interface.

    Two things had to match the real client's signature exactly for mypy's
    Protocol structural check to accept it, found by iterating against the
    actual errors rather than guessing: parameter names (`name`, not `key`
    - Protocol matching checks keyword-call compatibility too, even though
    this module only ever calls both methods positionally), and declaring
    `Awaitable[...]` returns via plain `def`, not `async def` (which
    desugars to the narrower `Coroutine[...]` - real redis.asyncio.Redis's
    methods are typed as returning plain Awaitable, and Awaitable is not a
    subtype of Coroutine, so a Coroutine-typed Protocol method rejected it).
    """

    def get(self, name: str) -> Awaitable[str | bytes | None]: ...
    def set(self, name: str, value: str) -> Awaitable[object]: ...


# Measured live against nomic-embed-text on real short support questions
# (see DECISIONS.md) before picking this number - it does NOT cleanly
# separate "same question, reworded" from "different but topically related
# question": genuine paraphrases scored as low as 0.62-0.82, while
# same-topic-different-intent pairs (e.g. "return policy" vs "cancellation
# policy") scored up to 0.67 - overlapping the paraphrase range entirely.
# Only near-verbatim wording variants ("What's your return policy?" vs
# "What is the return policy") landed safely above the noisy zone, at
# ~0.92. 0.90 is set deliberately conservative rather than loosened to
# catch more paraphrases: for a support bot, a false-positive cache hit
# (serving a wrong-but-plausible cached answer) is worse than a cache miss
# (a few extra seconds recomputing the right one) - this cache mostly
# catches near-identical repeats, not true paraphrase-level matching, and
# that's an intentional precision-over-recall tradeoff, not an oversight.
SIMILARITY_THRESHOLD = 0.90
MAX_ENTRIES_PER_NAMESPACE = 50


@dataclass
class _CacheEntry:
    query: str
    embedding: list[float]
    answer: str


def _redis_key(namespace: str) -> str:
    return f"semantic_cache:{namespace}"


def _customer_namespace(customer_id: str) -> str:
    return f"customer:{customer_id}"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


async def _search_namespace(
    redis: _RedisLike, namespace: str, query_embedding: list[float]
) -> str | None:
    raw = await redis.get(_redis_key(namespace))
    if not raw:
        return None
    entries = [_CacheEntry(**e) for e in json.loads(raw)]
    if not entries:
        return None

    query_vec = np.array(query_embedding)
    best_score = -1.0
    best_answer: str | None = None
    for entry in entries:
        score = _cosine_similarity(query_vec, np.array(entry.embedding))
        if score > best_score:
            best_score = score
            best_answer = entry.answer

    return best_answer if best_score >= SIMILARITY_THRESHOLD else None


async def get_cached_answer(
    redis: _RedisLike, customer_id: str, query_embedding: list[float]
) -> str | None:
    """Check the customer's own namespace first (most specific - always
    safe, since anything cached there was already this customer's own
    answer), then fall back to the shared global namespace (pure-doc
    answers, safe for anyone). Never checks another customer's namespace -
    there'd be no way to do that safely even if it were tempting for a
    cache-hit-rate win.
    """
    for namespace in (_customer_namespace(customer_id), GLOBAL_NAMESPACE):
        answer = await _search_namespace(redis, namespace, query_embedding)
        if answer is not None:
            return answer
    return None


async def store_answer(
    redis: _RedisLike,
    customer_id: str,
    touched_live_data: bool,
    query: str,
    query_embedding: list[float],
    answer: str,
) -> None:
    """Namespace choice is the actual security-relevant decision in this
    module: an answer is written to the customer-specific namespace if it
    touched live order data (touched_live_data - i.e. tool_call_count > 0
    for the graph run that produced it), and ONLY to the shared global
    namespace otherwise. An answer that referenced this customer's order
    status must never be written globally - a later cache hit there would
    hand one customer's order data to a completely different customer who
    happened to ask a similar-sounding question. Pure-doc answers (policy/
    FAQ, no tool calls) carry no such risk and are written globally on
    purpose, so many customers asking the same policy question share one
    cache entry instead of each paying for their own cache miss.
    """
    namespace = _customer_namespace(customer_id) if touched_live_data else GLOBAL_NAMESPACE
    raw = await redis.get(_redis_key(namespace))
    entries = json.loads(raw) if raw else []
    entries.append(asdict(_CacheEntry(query=query, embedding=query_embedding, answer=answer)))
    entries = entries[-MAX_ENTRIES_PER_NAMESPACE:]
    await redis.set(_redis_key(namespace), json.dumps(entries))
