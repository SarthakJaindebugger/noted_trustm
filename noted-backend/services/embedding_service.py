import logging
import os
from typing import List, Optional, Sequence

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from config import settings
from vector_db.client import get_qdrant_client
from vector_db.collections import (
    KNOWLEDGEBASE_COLLECTION,
    ensure_collection_exists,
    ensure_knowledgebase_collection,
)
from vector_db.payload_models import ServiceDocumentPayload

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Handles embedding generation and storage in Qdrant.

    The service currently focuses on the Finnish service knowledge base but can
    be extended to other collections later.
    """

    def __init__(
        self,
        *,
        qdrant_client: Optional[QdrantClient] = None,
        openai_client: Optional[OpenAI] = None,
        embedding_model: Optional[str] = None,
        knowledgebase_collection: str = KNOWLEDGEBASE_COLLECTION,
    ):
        self.qdrant_client = qdrant_client or get_qdrant_client()
        self.embedding_model = embedding_model or settings.models.embedding.name

        base_url = settings.models.embedding.url
        api_key = settings.models.embedding.api_key or "none"

        if not base_url:
            raise ValueError("Embedding base URL is not configured (missing LLAMA_EMBED_URL)")

        logger.info("Initialising embedding client with base URL %s and model %s", base_url, self.embedding_model)

        self._openai_client = openai_client or OpenAI(base_url=base_url, api_key=api_key)
        self.knowledgebase_collection = knowledgebase_collection
        self._collection_ready = False
        self._collection_vector_size: Optional[int] = None
        self._max_embedding_input_chars = max(
            256,
            int(os.getenv("EMBEDDING_MAX_INPUT_CHARS", "1500")),
        )

    def _prepare_embedding_input(self, text: str) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) > self._max_embedding_input_chars:
            logger.debug(
                "Truncating embedding input from %s to %s chars",
                len(cleaned),
                self._max_embedding_input_chars,
            )
            cleaned = cleaned[: self._max_embedding_input_chars]
        return cleaned

    def _ensure_collection_ready(self, vector_size: int) -> None:
        if self._collection_ready and self._collection_vector_size == vector_size:
            return

        collection_name = self.knowledgebase_collection
        if self.qdrant_client.collection_exists(collection_name=collection_name):
            info = self.qdrant_client.get_collection(collection_name=collection_name)
            existing_size = None
            if info.config and info.config.params and info.config.params.vectors:
                existing_size = info.config.params.vectors.size

            if existing_size is not None and existing_size != vector_size:
                alternate = f"{collection_name}_dim{vector_size}"
                logger.warning(
                    "Collection '%s' has vector size %s but embedding model produces %s. "
                    "Using '%s' instead.",
                    collection_name,
                    existing_size,
                    vector_size,
                    alternate,
                )
                ensure_collection_exists(
                    self.qdrant_client,
                    collection_name=alternate,
                    vector_size=vector_size,
                )
                self.knowledgebase_collection = alternate
                self._collection_ready = True
                self._collection_vector_size = vector_size
                return

        if collection_name == KNOWLEDGEBASE_COLLECTION:
            ensure_knowledgebase_collection(self.qdrant_client, vector_size=vector_size)
        else:
            ensure_collection_exists(
                self.qdrant_client,
                collection_name=collection_name,
                vector_size=vector_size,
            )
        self._collection_ready = True
        self._collection_vector_size = vector_size

    def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed an empty text snippet")

        prepared = self._prepare_embedding_input(text)
        if not prepared:
            raise ValueError("Cannot embed an empty text snippet")

        response = self._openai_client.embeddings.create(
            model=self.embedding_model,
            input=prepared,
        )
        if not response.data:
            raise RuntimeError("Embedding API did not return any vectors")
        return response.data[0].embedding

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        normalised: List[str] = [
            self._prepare_embedding_input(text)
            for text in texts
            if text and text.strip()
        ]
        if len(normalised) != len(texts):
            raise ValueError("All texts in a batch must be non-empty strings")

        response = self._openai_client.embeddings.create(
            model=self.embedding_model,
            input=list(normalised),
        )

        embeddings = [item.embedding for item in response.data]
        if len(embeddings) != len(texts):
            raise RuntimeError("Embedding API returned unexpected number of vectors")
        return embeddings

    def upsert_service_documents(
        self,
        documents: Sequence[ServiceDocumentPayload],
        *,
        batch_size: int = 32,
    ) -> None:
        if not documents:
            logger.info("No documents provided for upsert")
            return

        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            combined_texts = [doc.combined_text for doc in batch]
            embeddings = self.embed_batch(combined_texts)

            if embeddings:
                self._ensure_collection_ready(vector_size=len(embeddings[0]))

            points: List[rest.PointStruct] = []
            for doc, vector in zip(batch, embeddings):
                point = rest.PointStruct(
                    id=doc.record_id,
                    vector=vector,
                    payload=doc.to_payload(),
                )
                points.append(point)

            logger.info(
                "Upserting %s knowledge base documents into collection '%s'",
                len(points),
                self.knowledgebase_collection,
            )
            self.qdrant_client.upsert(
                collection_name=self.knowledgebase_collection,
                points=points,
            )

    def search_knowledgebase(
        self,
        text: str,
        *,
        limit: int = 5,
        score_threshold: Optional[float] = None,
    ) -> List[rest.ScoredPoint]:
        query_vector = self.embed_text(text)
        self._ensure_collection_ready(vector_size=len(query_vector))
        # qdrant-client compatibility:
        # - older versions expose `search(...)`
        # - newer versions expose `query_points(...)`
        if hasattr(self.qdrant_client, "search"):
            return self.qdrant_client.search(
                collection_name=self.knowledgebase_collection,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                score_threshold=score_threshold,
            )

        query_kwargs = {
            "collection_name": self.knowledgebase_collection,
            "query": query_vector,
            "limit": limit,
            "with_payload": True,
        }
        if score_threshold is not None:
            query_kwargs["score_threshold"] = score_threshold

        try:
            response = self.qdrant_client.query_points(**query_kwargs)
        except TypeError:
            # Some versions may not support score_threshold in query_points
            query_kwargs.pop("score_threshold", None)
            response = self.qdrant_client.query_points(**query_kwargs)

        points = getattr(response, "points", None)
        if points is None:
            points = response if isinstance(response, list) else []

        if score_threshold is not None:
            points = [
                point
                for point in points
                if float(getattr(point, "score", 0.0) or 0.0) >= score_threshold
            ]
        return list(points)
