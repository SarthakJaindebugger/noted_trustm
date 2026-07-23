"""Qdrant collection creation, payload schema, and similarity search."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from .config import QDRANT_COLLECTION, QDRANT_DISTANCE, QDRANT_DIMENSION, QDRANT_URL
from .utils import write_json


class QdrantStore:
    def __init__(self, url: str = QDRANT_URL, collection: str = QDRANT_COLLECTION):
        self.client = QdrantClient(url=url)
        self.collection = collection

    def create_collection(self, distance: str = QDRANT_DISTANCE, vector_size: int = QDRANT_DIMENSION):
        collections = self.client.get_collections().collections
        exists = any(collection.name == self.collection for collection in collections)
        if not exists:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=rest.VectorParams(size=vector_size, distance=distance),
            )

    def upsert_chunks(self, points: List[Dict[str, Any]]):
        self.client.upsert(
            collection_name=self.collection,
            points=points,
        )

    def search(self, query_vector: List[float], top_k: int = 5):
        response = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [hit for hit in response]

    def export_collection(self, output_path: Path):
        data = self.client.scroll(collection_name=self.collection, with_payload=True)
        return write_json([item.to_dict() for item in data], output_path)
