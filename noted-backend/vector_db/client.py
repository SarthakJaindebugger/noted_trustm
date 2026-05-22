import logging
from functools import lru_cache
from typing import Optional

from qdrant_client import QdrantClient

from config import settings

logger = logging.getLogger(__name__)


def _resolve_qdrant_url_components() -> dict:
    """
    Build keyword arguments for Qdrant client initialisation based on settings.
    Supports both URL-style and host/port configuration.
    """
    kwargs: dict = {}
    api_key: Optional[str] = settings.vector_db.api_key
    if api_key:
        kwargs["api_key"] = api_key

    prefer_grpc = settings.vector_db.prefer_grpc
    if prefer_grpc:
        kwargs["prefer_grpc"] = True

    url: Optional[str] = settings.vector_db.url
    if url:
        kwargs["url"] = url
        logger.debug("Configuring Qdrant client via URL %s", url)
        return kwargs

    host: str = settings.vector_db.host
    port: int = int(settings.vector_db.port)
    grpc_port: Optional[int] = settings.vector_db.grpc_port

    kwargs["host"] = host
    kwargs["port"] = port
    if grpc_port is not None:
        kwargs["grpc_port"] = grpc_port

    logger.debug("Configuring Qdrant client via host %s:%s", host, port)
    return kwargs


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Return a cached Qdrant client instance."""
    client_kwargs = _resolve_qdrant_url_components()
    logger.info("Initialising Qdrant client")
    return QdrantClient(**client_kwargs)
