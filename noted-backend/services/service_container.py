"""
Service container for dependency injection.

Central registry for all shared services. Initialized once at app startup.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Simple DI container — register once, get everywhere."""

    def __init__(self):
        self._services: Dict[str, Any] = {}

    # --- LLM Clients (centralized) ---

    def register_llm_client(self) -> OpenAI:
        """Register the generation LLM client (shared by summarizer, processor, chunker)."""
        if "llm_client" not in self._services:
            from config import settings
            self._services["llm_client"] = OpenAI(
                base_url=settings.models.generation.url,
                api_key=settings.models.generation.api_key or "none",
            )
            logger.info("Registered LLM client: %s", settings.models.generation.url)
        return self._services["llm_client"]

    def get_llm_client(self) -> Optional[OpenAI]:
        return self._services.get("llm_client")

    def register_embed_client(self) -> OpenAI:
        """Register the embedding LLM client."""
        if "embed_client" not in self._services:
            from config import settings
            self._services["embed_client"] = OpenAI(
                base_url=settings.models.embedding.url or settings.models.generation.url,
                api_key=settings.models.embedding.api_key or settings.models.generation.api_key or "none",
            )
            logger.info("Registered embedding client: %s", settings.models.embedding.url)
        return self._services["embed_client"]

    def get_embed_client(self) -> Optional[OpenAI]:
        return self._services.get("embed_client")

    # --- Chunker ---

    def register_chunker(self):
        if "chunker" not in self._services:
            from audio.chunker import AudioChunker
            self._services["chunker"] = AudioChunker()
            logger.info("Registered chunker service")
        return self._services["chunker"]

    def get_chunker(self):
        return self._services.get("chunker")

    # --- Embedding Service ---

    def register_embedding_service(self):
        if "embedding" not in self._services:
            from services.embedding_service import EmbeddingService
            self._services["embedding"] = EmbeddingService()
            logger.info("Registered embedding service")
        return self._services["embedding"]

    def get_embedding_service(self):
        return self._services.get("embedding")

    # --- Summarizer ---

    def register_summarizer(self):
        if "summarizer" not in self._services:
            from services.summarizer import SummarizerService
            client = self.get_llm_client() or self.register_llm_client()
            embedding = self.get_embedding_service()
            self._services["summarizer"] = SummarizerService(
                openai_client=client,
                embedding_service=embedding,
            )
            logger.info("Registered summarizer service")
        return self._services["summarizer"]

    def get_summarizer(self):
        return self._services.get("summarizer")

    # --- Session Manager (singleton) ---

    def register_session_manager(self):
        if "session_manager" not in self._services:
            from services.session_manager_async import AsyncSessionManager
            self._services["session_manager"] = AsyncSessionManager()
            logger.info("Registered session manager (singleton)")
        return self._services["session_manager"]

    def get_session_manager(self):
        return self._services.get("session_manager")

    # --- Lifecycle ---

    def cleanup(self):
        self._services.clear()
        logger.info("Service container cleaned up")


# Global singleton
service_container = ServiceContainer()
