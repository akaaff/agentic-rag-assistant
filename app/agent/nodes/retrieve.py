from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agent.state import GraphState
from app.retrieval.embeddings import OllamaEmbeddingsClient
from app.retrieval.hybrid import hybrid_search
from app.retrieval.rerank import rerank
from app.retrieval.store import SearchResult, async_session_factory

TOP_K = 5
CANDIDATE_K = 15


def _last_user_text(state: GraphState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("No user message found in state")


async def retrieve_node(state: GraphState) -> dict[str, list[SearchResult]]:
    query = _last_user_text(state)
    embeddings_client = OllamaEmbeddingsClient()
    [embedding] = await embeddings_client.embed([query])

    async with async_session_factory() as session:
        fused = await hybrid_search(
            session, query, embedding, top_k=CANDIDATE_K, candidate_k=CANDIDATE_K
        )
    reranked = rerank(query, fused, top_k=TOP_K)
    return {"retrieved_docs": reranked}
