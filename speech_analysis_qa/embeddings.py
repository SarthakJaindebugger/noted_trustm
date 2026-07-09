"""Qwen embedding wrapper and batch encoder."""

from pathlib import Path
from typing import Iterable, List

from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL
from .utils import normalize_text


class QwenEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model_name = model_name
        self.embedder = SentenceTransformer(
            self.model_name,
            model_kwargs={"trust_remote_code": True},
            device="cuda" if __import__("torch").cuda.is_available() else "cpu"
        )

    def embed_texts(self, texts: Iterable[str], batch_size: int = 32):
        normalized = [normalize_text(text) for text in texts if normalize_text(text)]
        if not normalized:
            return []
        return self.embedder.encode(
            normalized,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=batch_size,
            show_progress_bar=False,
        )

    def embed_text(self, text: str):
        return self.embed_texts([text])[0]
