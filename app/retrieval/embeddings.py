from __future__ import annotations

import httpx

from app.config import settings


class OllamaEmbeddingsClient:
    """Thin async client for Ollama's batched embeddings endpoint (/api/embed).

    Batched (one request for N texts) rather than one request per chunk -
    ingest.py embeds a whole corpus at once, and there's no reason to pay
    per-text round-trip overhead against a local model.
    """

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_embed_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
        embeddings: list[list[float]] = data["embeddings"]
        return embeddings
