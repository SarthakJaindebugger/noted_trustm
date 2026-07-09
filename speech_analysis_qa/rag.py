"""RAG orchestration, prompt building, and QA answer generation."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .config import HF_TOKEN, MAX_CONTEXT_CHUNKS, TOP_K
from .embeddings import QwenEmbedder
from .retrieval import QdrantStore
from .utils import normalize_text, write_json


class RagPipeline:
    def __init__(self, collection_name: str = None):
        self.embedder = QwenEmbedder()
        self.store = QdrantStore(collection=collection_name) if collection_name else QdrantStore()

    def build_payload(self, chunk: dict, metadata: dict) -> dict:
        return {
            "id": str(chunk["chunk_id"]),
            "vector": chunk["embedding"],
            "payload": {
                "text": chunk["text"],
                "speaker": chunk["speaker"],
                "start": chunk["start"],
                "end": chunk["end"],
                "source_start": chunk["source_start"],
                "source_end": chunk["source_end"],
                "metadata": metadata,
            },
        }

    def upsert_chunks(self, chunks: List[dict], metadata: dict):
        points = [self.build_payload(chunk, metadata) for chunk in chunks]
        self.store.upsert_chunks(points)

    def retrieve(self, question: str, top_k: int = TOP_K) -> List[dict]:
        query_embedding = self.embedder.embed_text(question).tolist()
        hits = self.store.search(query_embedding, top_k=top_k)
        return [hit.payload for hit in hits]

    def build_context(self, hits: List[dict], max_chunks: int = MAX_CONTEXT_CHUNKS) -> str:
        selected = hits[:max_chunks]
        context_lines = []
        for idx, item in enumerate(selected, start=1):
            context_lines.append(
                f"[{idx}] {item['speaker']} {item['start']:.2f}-{item['end']:.2f}: {item['text']}"
            )
        return "\n".join(context_lines)

    def build_prompt(self, question: str, context: str) -> str:
        return (
            "You are a precise assistant answering questions about a speech transcript. "
            "Use only the provided context. If the answer is not present, say 'Not specified'.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n"
        )

    def answer_question(self, question: str, hits: List[dict]) -> dict:
        context = self.build_context(hits)
        prompt = self.build_prompt(question, context)
        return {
            "question": question,
            "context": context,
            "answer": prompt,
            "confidence": None,
        }

    def save_session(self, session_output: dict, path: Path) -> Path:
        return write_json(session_output, path)


def main():
    runner = RagPipeline()
    print("RAG pipeline initialized")


if __name__ == "__main__":
    main()
