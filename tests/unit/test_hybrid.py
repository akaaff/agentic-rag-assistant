import uuid

from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.store import SearchResult


def _result(label: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_OID, label),
        content=f"content for {label}",
        chunk_index=0,
        doc_type="policy",
        category="general",
        title="Doc",
        source_file="doc.md",
        score=score,
    )


def test_rrf_fuses_two_ranked_lists() -> None:
    labels_and_scores = [("A", 0.9), ("B", 0.5), ("C", 0.3), ("D", 0.4)]
    a, b, c, d = (_result(label, score) for label, score in labels_and_scores)

    # A and B are tied (rank 1 in one list, rank 2 in the other) - a result
    # in both lists should always outrank one seen in only a single list.
    vector_results = [a, b, c]
    keyword_results = [b, a, d]

    fused = reciprocal_rank_fusion([vector_results, keyword_results])

    assert [r.chunk_id for r in fused] == [a.chunk_id, b.chunk_id, c.chunk_id, d.chunk_id]


def test_rrf_preserves_single_list_order() -> None:
    a, b, c = (_result(label, 0.5) for label in ["A", "B", "C"])

    fused = reciprocal_rank_fusion([[a, b, c]])

    assert [r.chunk_id for r in fused] == [a.chunk_id, b.chunk_id, c.chunk_id]


def test_rrf_handles_empty_lists() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_result_only_in_one_list_is_still_included() -> None:
    a = _result("A", 0.9)
    b = _result("B", 0.1)

    fused = reciprocal_rank_fusion([[a], [b]])

    assert {r.chunk_id for r in fused} == {a.chunk_id, b.chunk_id}
