from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import lru_cache

from app.retrieval.store import SearchResult

RERANKER_MODEL = "BAAI/bge-reranker-base"

ScoreFn = Callable[[list[tuple[str, str]]], Sequence[float]]


@lru_cache(maxsize=1)
def _default_score_fn() -> ScoreFn:
    # Imported lazily (not at module top) so importing this module doesn't
    # force loading torch/sentence-transformers unless reranking is
    # actually used - and cached (@lru_cache) so the model is loaded once
    # per process, not once per request once this is called from FastAPI.
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(RERANKER_MODEL)

    def score(pairs: list[tuple[str, str]]) -> Sequence[float]:
        # sentence-transformers ships no type stubs - predict() is Any.
        return model.predict(pairs)  # type: ignore[no-any-return]

    return score


def rerank(
    query: str,
    results: list[SearchResult],
    top_k: int = 5,
    score_fn: ScoreFn | None = None,
) -> list[SearchResult]:
    """Cross-encoder rerank of an already-fused candidate list.

    score_fn is injectable so unit tests can verify the sort/truncate logic
    with a fake, deterministic scorer instead of downloading and running the
    real ~500MB bge-reranker-base model - the model's actual output quality
    is verified live (see the dogfood checkpoint), not asserted against in a
    unit test.
    """
    if not results:
        return []

    scorer = score_fn or _default_score_fn()
    pairs = [(query, r.content) for r in results]
    scores = scorer(pairs)

    ranked = sorted(zip(results, scores, strict=True), key=lambda item: item[1], reverse=True)
    reranked = [replace(result, score=float(score)) for result, score in ranked]
    return reranked[:top_k]
