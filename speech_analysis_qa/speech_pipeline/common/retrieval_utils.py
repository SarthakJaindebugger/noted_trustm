# -*- coding: utf-8 -*-
"""
common/retrieval_utils.py
===========================
In-memory Qdrant retrieval used only by stage 4 (structured Q&A), pulled
out of privacy_rag_2_outputs.py so stage4_qa_private.py stays focused on
the questionnaire logic.
"""

from typing import List


class Retriever:
    """Wraps: embed -> in-memory Qdrant collection -> retrieve.
    Falls back to returning the full transcript untouched when it is short
    enough to fit in the model's context, avoiding lossy retrieval."""

    def __init__(self, embed_model_name: str, full_text: str,
                 max_chars_for_full_context: int, chunk_size: int, overlap: int):
        from speech_analysis_qa.speech_pipeline.common.text_utils import chunk_text

        self.embed_model_name = embed_model_name
        self.full_text = full_text
        self.use_full_transcript = len(full_text) <= max_chars_for_full_context
        self.chunks = [] if self.use_full_transcript else chunk_text(full_text, chunk_size, overlap)

        self._tokenizer = None
        self._model = None
        self._client = None
        self._collection = "transcript_chunks"

        if not self.use_full_transcript:
            self._build_index()

    # -- embedder lifecycle -------------------------------------------------
    def _load_embedder(self):
        import torch
        from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

        if self._model is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self.embed_model_name)
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            if torch.cuda.is_available():
                device_map = "auto"
            else:
                # Avoid loading the large embedder on MPS; use CPU with quantization instead.
                device_map = {"": "cpu"}

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                llm_int8_enable_fp32_cpu_offload=True,
            )

            try:
                self._model = AutoModel.from_pretrained(
                    self.embed_model_name,
                    quantization_config=bnb_config,
                    device_map=device_map,
                    low_cpu_mem_usage=True,
                )
            except Exception:
                self._model = AutoModel.from_pretrained(self.embed_model_name, device_map={"": "cpu"})
            self._model.eval()

    def _unload_embedder(self):
        import gc
        import torch

        if self._model is not None:
            try:
                self._model.to("cpu")
            except Exception:
                pass
            self._model = None
            self._tokenizer = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass

    def _embed(self, text: str) -> List[float]:
        import torch

        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model(**inputs)
        return outputs.last_hidden_state.mean(dim=1).cpu().float().numpy()[0].tolist()

    # -- index build / query -------------------------------------------------
    def _build_index(self):
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance

        self._load_embedder()
        vector_size = self._model.config.hidden_size

        self._client = QdrantClient(":memory:")
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

        points = [
            PointStruct(id=i, vector=self._embed(c), payload={"text": c})
            for i, c in enumerate(self.chunks)
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def _retrieve(self, query: str, top_k: int) -> List[str]:
        self._load_embedder()
        query_emb = self._embed(query)

        results = self._client.query_points(
            collection_name=self._collection, query=query_emb, limit=top_k,
        )
        return [hit.payload["text"] for hit in results.points]

    def close(self):
        self._unload_embedder()
        self._client = None

    def get_context(self, query: str, top_k: int) -> str:
        """Best available context for a prompt: full transcript if it fits,
        otherwise the top-k retrieved chunks."""
        if self.use_full_transcript:
            return self.full_text
        return "\n\n".join(self._retrieve(query, top_k=top_k))
