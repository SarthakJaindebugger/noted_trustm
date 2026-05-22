import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

logger = logging.getLogger(__name__)

KNOWLEDGEBASE_COLLECTION = "suomi_services"


def _create_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
    distance: rest.Distance = rest.Distance.COSINE,
) -> None:
    payload_schema = {
        "service_name": rest.PayloadSchemaType.TEXT,
        "service_link": rest.PayloadSchemaType.TEXT,
        "description": rest.PayloadSchemaType.TEXT,
        "mini_description": rest.PayloadSchemaType.TEXT,
        "short_description": rest.PayloadSchemaType.TEXT,
        "other_links": rest.PayloadSchemaType.KEYWORD,
        "combined_text": rest.PayloadSchemaType.TEXT,
        "date": rest.PayloadSchemaType.TEXT,
        "source": rest.PayloadSchemaType.TEXT,
    }

    logger.info(
        "Creating Qdrant collection '%s' with vector size %s", collection_name, vector_size
    )
    client.create_collection(
        collection_name=collection_name,
        vectors_config=rest.VectorParams(size=vector_size, distance=distance),
    )


def ensure_collection_exists(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
    distance: rest.Distance = rest.Distance.COSINE,
) -> None:
    if vector_size <= 0:
        raise ValueError("vector_size must be a positive integer")

    if client.collection_exists(collection_name=collection_name):
        info = client.get_collection(collection_name=collection_name)
        existing_size: Optional[int] = None
        if info.config and info.config.params and info.config.params.vectors:
            existing_size = info.config.params.vectors.size

        if existing_size is not None and existing_size != vector_size:
            logger.warning(
                (
                    "Collection '%s' exists but vector size (%s) differs from requested size (%s). "
                    "Consider recreating the collection to avoid inconsistent data."
                ),
                collection_name,
                existing_size,
                vector_size,
            )
        else:
            logger.debug("Collection '%s' already present", collection_name)
        return

    _create_collection(client, collection_name, vector_size, distance)


def ensure_knowledgebase_collection(client: QdrantClient, vector_size: int) -> None:
    """Ensure the knowledge base collection exists with the expected vector size."""
    ensure_collection_exists(
        client=client,
        collection_name=KNOWLEDGEBASE_COLLECTION,
        vector_size=vector_size,
        distance=rest.Distance.COSINE,
    )
