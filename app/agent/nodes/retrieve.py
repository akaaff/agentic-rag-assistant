from __future__ import annotations

from app.agent.context import last_user_text
from app.agent.state import GraphState
from app.retrieval.embeddings import OllamaEmbeddingsClient
from app.retrieval.hybrid import hybrid_search
from app.retrieval.rerank import rerank
from app.retrieval.store import SearchResult, async_session_factory

TOP_K = 5
CANDIDATE_K = 15


async def retrieve_node(state: GraphState) -> dict[str, list[SearchResult]]:
    query = last_user_text(state)
    embeddings_client = OllamaEmbeddingsClient()
    [embedding] = await embeddings_client.embed([query])

    async with async_session_factory() as session:
        fused = await hybrid_search(
            session, query, embedding, top_k=CANDIDATE_K, candidate_k=CANDIDATE_K
        )
    reranked = rerank(query, fused, top_k=TOP_K)
    return {"retrieved_docs": reranked}
