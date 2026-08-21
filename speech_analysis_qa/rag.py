# -*- coding: utf-8 -*-
"""
speech_analysis_qa/rag.py
=========================
Minimal RAG pipeline support used by speech_analysis_qa.speech_pipeline.run_pipeline.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional


class QwenEmbedder:
    def __init__(self, model_name: str, hf_token: Optional[str] = None):
        import torch
        from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

        self.model_name = model_name
        self.hf_token = hf_token

        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_auth_token=hf_token or None)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            llm_int8_enable_fp32_cpu_offload=True,
        )

        if torch.cuda.is_available():
            device_map = "auto"
        else:
            device_map = {"": "cpu"}

        try:
            self.model = AutoModel.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map=device_map,
                low_cpu_mem_usage=True,
                use_auth_token=hf_token or None,
            )
        except Exception:
            self.model = AutoModel.from_pretrained(model_name, device_map={"": "cpu"})

        self.model.eval()

    def embed_texts(self, texts: Iterable[str]):
        import torch

        encoded = self.tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        encoded = {k: v.to(self.model.device) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = self.model(**encoded)

        embeddings = getattr(outputs, "last_hidden_state", outputs[0])
        embeddings = embeddings.mean(dim=1).cpu()
        return embeddings


class QdrantStore:
    def __init__(
        self,
        collection_name: str = "speech_chunks",
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        qdrant_host: Optional[str] = None,
        qdrant_port: Optional[int] = None,
    ):
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance

        qdrant_url = qdrant_url or os.getenv("QDRANT_URL")
        qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        qdrant_host = qdrant_host or os.getenv("QDRANT_HOST")
        qdrant_port = qdrant_port or int(os.getenv("QDRANT_PORT", "6333"))

        self.client = None
        self.enabled = True

        # Try remote server first, then fall back to local embedded mode
        if qdrant_url or qdrant_host:
            client_kwargs: Dict[str, Any] = {}
            if qdrant_url:
                client_kwargs["url"] = qdrant_url
            else:
                client_kwargs["host"] = qdrant_host
                client_kwargs["port"] = qdrant_port
            if qdrant_api_key:
                client_kwargs["api_key"] = qdrant_api_key
            try:
                self.client = QdrantClient(**client_kwargs, timeout=5)
                self.client.get_collections()
            except Exception as exc:
                print(f"WARNING: Remote Qdrant unavailable ({exc}), using local embedded mode.")
                self.client = None

        if self.client is None:
            try:
                import pathlib
                repo_root = pathlib.Path(__file__).resolve().parents[1]
                storage_path = os.getenv("QDRANT_STORAGE_PATH", str(repo_root / "qdrant_data"))
                os.makedirs(storage_path, exist_ok=True)
                self.client = QdrantClient(path=storage_path)
                print(f"Using local embedded Qdrant (storage: {storage_path})")
            except Exception as exc:
                print(f"WARNING: Could not initialize Qdrant at all; persistence disabled. {exc}")
                self.enabled = False

        self.collection_name = collection_name
        self._distance = Distance.COSINE

    def create_collection(self, vector_size: int, distance: str = "COSINE"):
        if not self.enabled or self.client is None:
            print("WARNING: Qdrant is disabled; skipping collection creation.")
            return

        from qdrant_client.http.models import VectorParams

        try:
            self.client.get_collection(collection_name=self.collection_name)
            return
        except Exception:
            pass

        distance_enum = getattr(type(self._distance), distance, self._distance)
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance_enum),
            )
        except Exception as exc:
            print("WARNING: failed to create Qdrant collection; disabling Qdrant persistence.", exc)
            self.enabled = False

    def upsert_chunks(self, chunks: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None):
        if not self.enabled or self.client is None:
            print("WARNING: Qdrant is disabled; skipping upsert of chunk embeddings.")
            return

        from qdrant_client.http.models import PointStruct

        metadata = metadata or {}
        points = []
        for chunk in chunks:
            point_id = chunk.get("chunk_id") or chunk.get("id") or os.urandom(8).hex()
            payload = {"text": chunk.get("text", "")}
            payload.update(chunk.get("metadata", {}))
            payload.update(metadata)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk["embedding"],
                    payload=payload,
                )
            )

        try:
            self.client.upsert(collection_name=self.collection_name, points=points)
        except Exception as exc:
            print("WARNING: failed to upsert chunk embeddings to Qdrant; disabling Qdrant persistence.", exc)
            self.enabled = False


class RagPipeline:
    def __init__(
        self,
        embed_model_name: Optional[str] = None,
        collection_name: str = "speech_chunks",
        hf_token: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        qdrant_host: Optional[str] = None,
        qdrant_port: Optional[int] = None,
    ):
        from speech_analysis_qa.speech_pipeline.common.config import EMBED_MODEL_NAME

        self.embedder = QwenEmbedder(embed_model_name or EMBED_MODEL_NAME, hf_token=hf_token or os.getenv("HF_TOKEN"))
        self.store = QdrantStore(
            collection_name=collection_name,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
        )

    def upsert_chunks(self, chunks: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None):
        self.store.upsert_chunks(chunks, metadata)
