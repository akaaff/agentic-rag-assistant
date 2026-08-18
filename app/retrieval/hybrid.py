from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.store import SearchResult, keyword_search, vector_search

DEFAULT_RRF_K = 60
DEFAULT_CANDIDATE_K = 20


def reciprocal_rank_fusion(
    ranked_lists: list[list[SearchResult]], k: int = DEFAULT_RRF_K
) -> list[SearchResult]:
    """Fuse multiple ranked result lists via Reciprocal Rank Fusion.

    RRF over blending raw scores directly: vector cosine-similarity and
    ts_rank live on entirely different, incomparable scales. RRF only uses
    each result's *rank* within its own list, sidestepping the need to
    normalize or weight two unrelated scoring functions against each other.
    """
    scores: dict[uuid.UUID, float] = {}
    first_seen: dict[uuid.UUID, SearchResult] = {}

    for ranked_list in ranked_lists:
        for rank, result in enumerate(ranked_list, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(result.chunk_id, result)

    return sorted(first_seen.values(), key=lambda r: scores[r.chunk_id], reverse=True)


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    query_embedding: Sequence[float],
    top_k: int = 10,
    candidate_k: int = DEFAULT_CANDIDATE_K,
) -> list[SearchResult]:
    """Vector + keyword search, each over-fetching candidate_k, fused by RRF,
    then truncated to top_k. Reranking (Day 3) operates on this fused list."""
    vector_results = await vector_search(session, query_embedding, top_k=candidate_k)
    keyword_results = await keyword_search(session, query_text, top_k=candidate_k)
    fused = reciprocal_rank_fusion([vector_results, keyword_results])
    return fused[:top_k]
