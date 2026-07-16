from __future__ import annotations

from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient, models

from tnoc.settings import Settings


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class KnowledgeRetriever(Protocol):
    async def search(self, tenant_id: str, query: str) -> list[dict[str, Any]]: ...


class NullKnowledgeRetriever:
    async def search(self, tenant_id: str, query: str) -> list[dict[str, Any]]:
        return []


class LangChainEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        provider_options: dict[str, Any] = {}
        if settings.embedding_provider == "openai":
            if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY required for OpenAI embeddings")
            provider_options["api_key"] = settings.openai_api_key.get_secret_value()
        if settings.embedding_provider.casefold().replace("-", "_") in {
            "gemini",
            "google",
            "google_genai",
        }:
            key = next(
                (
                    secret.get_secret_value()
                    for secret in (settings.google_api_key, settings.gemini_api_key)
                    if secret is not None and secret.get_secret_value()
                ),
                None,
            )
            if key is None:
                raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY required for Google embeddings")
            provider_options["api_key"] = key
        self._client: Embeddings = init_embeddings(
            model=settings.embedding_model,
            provider=settings.embedding_provider,
            **provider_options,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._client.aembed_documents(texts)


class KnowledgeIndex:
    def __init__(self, settings: Settings, embeddings: EmbeddingProvider) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key and settings.qdrant_api_key.get_secret_value()
                else None
            ),
        )

    def chunk(self, text: str) -> list[str]:
        size = self._settings.rag_chunk_characters
        overlap = self._settings.rag_chunk_overlap_characters
        if overlap >= size:
            raise ValueError("RAG chunk overlap must be smaller than chunk size")
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start = end - overlap
        return chunks

    async def index_document(
        self,
        *,
        document_id: UUID,
        tenant_id: str,
        title: str,
        source_uri: str,
        text: str,
        metadata: dict[str, Any],
    ) -> int:
        chunks = self.chunk(text)
        vectors = await self._embeddings.embed(chunks)
        if not vectors:
            return 0
        if not await self._client.collection_exists(self._settings.qdrant_collection):
            try:
                await self._client.create_collection(
                    collection_name=self._settings.qdrant_collection,
                    vectors_config=models.VectorParams(
                        size=len(vectors[0]), distance=models.Distance.COSINE
                    ),
                )
            except Exception:
                if not await self._client.collection_exists(self._settings.qdrant_collection):
                    raise
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            point_key = str(uuid5(NAMESPACE_URL, f"tnoc:{document_id}:{index}"))
            points.append(
                models.PointStruct(
                    id=point_key,
                    vector=vector,
                    payload={
                        "tenant_id": tenant_id,
                        "document_id": str(document_id),
                        "chunk_index": index,
                        "title": title,
                        "source_uri": source_uri,
                        "text": chunk,
                        "metadata": metadata,
                    },
                )
            )
        await self._client.upsert(
            collection_name=self._settings.qdrant_collection,
            points=points,
            wait=True,
        )
        return len(points)

    async def search(self, tenant_id: str, query: str) -> list[dict[str, Any]]:
        if not await self._client.collection_exists(self._settings.qdrant_collection):
            return []
        vector = (await self._embeddings.embed([query]))[0]
        result = await self._client.query_points(
            collection_name=self._settings.qdrant_collection,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))
                ]
            ),
            limit=self._settings.rag_result_limit,
            with_payload=True,
        )
        return [{"score": point.score, **(point.payload or {})} for point in result.points]
