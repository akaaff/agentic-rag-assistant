import uuid
from collections.abc import Sequence

from app.retrieval.rerank import rerank
from app.retrieval.store import SearchResult


def _result(label: str) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_OID, label),
        content=f"content for {label}",
        chunk_index=0,
        doc_type="policy",
        category="general",
        title="Doc",
        source_file="doc.md",
        score=0.0,
    )


def _fake_scorer(score_by_content: dict[str, float]) -> object:
    def score_fn(pairs: list[tuple[str, str]]) -> Sequence[float]:
        return [score_by_content[doc] for _query, doc in pairs]

    return score_fn


def test_rerank_sorts_by_score_descending() -> None:
    a, b, c = (_result(label) for label in ["A", "B", "C"])
    # Deliberately fed in a "wrong" order - rerank should fix it based on score.
    candidates = [a, b, c]
    scorer = _fake_scorer(
        {
            a.content: 0.1,
            b.content: 0.9,
            c.content: 0.5,
        }
    )

    reranked = rerank("some query", candidates, top_k=10, score_fn=scorer)  # type: ignore[arg-type]

    assert [r.chunk_id for r in reranked] == [b.chunk_id, c.chunk_id, a.chunk_id]
    assert [r.score for r in reranked] == [0.9, 0.5, 0.1]


def test_rerank_truncates_to_top_k() -> None:
    candidates = [_result(label) for label in ["A", "B", "C", "D"]]
    scorer = _fake_scorer({r.content: float(i) for i, r in enumerate(candidates)})

    reranked = rerank("q", candidates, top_k=2, score_fn=scorer)  # type: ignore[arg-type]

    assert len(reranked) == 2


def test_rerank_handles_empty_results() -> None:
    assert rerank("q", [], top_k=5) == []
