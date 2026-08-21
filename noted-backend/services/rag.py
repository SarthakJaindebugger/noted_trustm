import numpy as np
from typing import List, Dict, Any, Optional
import json
import logging
import os
import sys
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import asyncio

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "speech_analysis_qa" / "speech_pipeline"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "crm_aggregated")
CRM_FORMS_DIR = REPO_ROOT / "knowledgebase" / "submitted_crm_forms"
AGGREGATED_EMBEDDINGS_DIR = REPO_ROOT / "knowledgebase" / "aggregated_data_embeddings"
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(REPO_ROOT / "models")))

# Pre-import transformers classes at module level to avoid thread race on lazy imports
try:
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: F401
except ImportError:
    pass

_rag_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("RAG_WORKERS", "4")),
    thread_name_prefix="rag",
)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _crm_form_to_text(form_data: Dict[str, Any]) -> str:
    """Convert a CRM form JSON into a single searchable text chunk."""
    parts = []

    questionnaire = form_data.get("questionnaire", {})
    for question, answer in questionnaire.items():
        if answer and answer != "Not mentioned in transcript.":
            parts.append(f"{question}: {answer}")

    metadata = form_data.get("metadata", {})
    if metadata.get("audio_file"):
        parts.append(f"Audio file: {metadata['audio_file']}")
    if metadata.get("date_time"):
        parts.append(f"Date: {metadata['date_time']}")
    if metadata.get("visit_duration"):
        parts.append(f"Visit duration: {metadata['visit_duration']}")

    form = form_data.get("form", {})
    if form.get("gender"):
        parts.append(f"Gender: {form['gender']}")
    if form.get("ageGroup"):
        parts.append(f"Age group: {form['ageGroup']}")
    if form.get("birthCountry"):
        parts.append(f"Birth country: {form['birthCountry']}")
    if form.get("motherTongue"):
        parts.append(f"Mother tongue: {form['motherTongue']}")
    if form.get("customerCount"):
        parts.append(f"Customer count: {form['customerCount']}")
    if form.get("controlLocation"):
        parts.append(f"Location: {form['controlLocation']}")

    return "\n".join(parts)


class RAGService:
    """
    RAG Service for admin dashboard chatbot.
    Uses locally hosted models (no HF API calls).
    Data source: aggregated CRM form embeddings from submitted_crm_forms.
    """

    def __init__(self):
        self.hf_token = os.getenv("HF_TOKEN", "")

        self._qdrant_client = None
        self._qdrant_available = None
        self._llm_tokenizer = None
        self._llm_model = None
        self._embed_tokenizer = None
        self._embed_model = None
        self._embeddings_cache = None
        self._cache_time = 0
        self._models_ready = False

        from speech_analysis_qa.speech_pipeline.common.config import QA_MODEL_NAME, EMBED_MODEL_NAME
        self.llm_model_name = os.getenv("QA_MODEL_NAME", QA_MODEL_NAME)
        self.embed_model_name = os.getenv("EMBED_MODEL_NAME", EMBED_MODEL_NAME)

        self.llm_local_path = MODELS_DIR / self.llm_model_name.replace("/", "--")
        self.embed_local_path = MODELS_DIR / self.embed_model_name.replace("/", "--")

        AGGREGATED_EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("RAG service initialized (collection=%s)", COLLECTION_NAME)
        logger.info("  LLM: %s (local: %s)", self.llm_model_name, self.llm_local_path)
        logger.info("  Embed: %s (local: %s)", self.embed_model_name, self.embed_local_path)
        logger.info("  CRM forms: %s", CRM_FORMS_DIR)
        logger.info("  Embeddings: %s", AGGREGATED_EMBEDDINGS_DIR)

    # ──────────────────────────────────────────────────────────────────
    # Model loading
    # ──────────────────────────────────────────────────────────────────

    def _ensure_model_downloaded(self, model_name: str, local_path: Path):
        """Download model from HuggingFace to local models/ directory if not already present."""
        if local_path.exists() and any(local_path.iterdir()):
            return str(local_path)

        logger.info("[RAG] Downloading %s to %s ...", model_name, local_path)
        local_path.mkdir(parents=True, exist_ok=True)
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=model_name,
            local_dir=str(local_path),
            token=self.hf_token or None,
        )
        logger.info("[RAG] Download complete: %s", local_path)
        return str(local_path)

    def _load_llm(self):
        """Load the Qwen LLM from local models/ directory."""
        if self._llm_tokenizer is None or self._llm_model is None:
            import torch
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            except ImportError:
                from transformers.models.auto import AutoModelForCausalLM
                from transformers import AutoTokenizer, BitsAndBytesConfig

            model_path = self._ensure_model_downloaded(self.llm_model_name, self.llm_local_path)
            logger.info("[RAG] Loading LLM from: %s", model_path)

            self._llm_tokenizer = AutoTokenizer.from_pretrained(model_path)
            if self._llm_tokenizer.pad_token is None:
                self._llm_tokenizer.pad_token = self._llm_tokenizer.eos_token

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                llm_int8_enable_fp32_cpu_offload=True,
            )

            device_map = "auto" if torch.cuda.is_available() else {"": "cpu"}

            self._llm_model = AutoModelForCausalLM.from_pretrained(
                model_path,
                quantization_config=bnb_config,
                device_map=device_map,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
            )
            logger.info("[RAG] LLM loaded on %s", "GPU" if torch.cuda.is_available() else "CPU")

        return self._llm_tokenizer, self._llm_model

    def _load_embed_model(self):
        """Load the embedding model from local models/ directory."""
        if self._embed_tokenizer is None or self._embed_model is None:
            import torch
            try:
                from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig
            except ImportError:
                from transformers.models.auto import AutoModel
                from transformers import AutoTokenizer, BitsAndBytesConfig

            model_path = self._ensure_model_downloaded(self.embed_model_name, self.embed_local_path)
            logger.info("[RAG] Loading embedding model from: %s", model_path)

            self._embed_tokenizer = AutoTokenizer.from_pretrained(model_path)
            if self._embed_tokenizer.pad_token is None:
                self._embed_tokenizer.pad_token = self._embed_tokenizer.eos_token

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                llm_int8_enable_fp32_cpu_offload=True,
            )

            device_map = "auto" if torch.cuda.is_available() else {"": "cpu"}

            try:
                self._embed_model = AutoModel.from_pretrained(
                    model_path,
                    quantization_config=bnb_config,
                    device_map=device_map,
                    low_cpu_mem_usage=True,
                )
            except Exception:
                self._embed_model = AutoModel.from_pretrained(model_path, device_map={"": "cpu"})

            self._embed_model.eval()
            logger.info("[RAG] Embedding model loaded successfully")

        return self._embed_tokenizer, self._embed_model

    def warmup(self):
        """Pre-load both models into memory sequentially. Called at startup."""
        logger.info("[RAG] Warming up — loading embedding model...")
        self._load_embed_model()
        logger.info("[RAG] Warming up — loading LLM...")
        self._load_llm()
        self._models_ready = True
        logger.info("[RAG] Both models loaded and ready for inference")

    async def warmup_async(self):
        """Async warmup — loads models in background thread (sequentially to avoid import races)."""
        loop = asyncio.get_event_loop()
        logger.info("[RAG] Starting model warmup in background...")
        await loop.run_in_executor(_rag_executor, self.warmup)
        logger.info("[RAG] Warmup complete — models ready for inference")

    # ──────────────────────────────────────────────────────────────────
    # Embedding generation
    # ──────────────────────────────────────────────────────────────────

    def _embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text using local model."""
        import torch
        tokenizer, model = self._load_embed_model()

        encoded = tokenizer(
            [text],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        encoded = {k: v.to(model.device) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = model(**encoded)

        embeddings = getattr(outputs, "last_hidden_state", outputs[0])
        embedding = embeddings.mean(dim=1).cpu()[0]
        return embedding.tolist()

    def _get_query_embedding(self, text: str) -> List[float]:
        """Get embedding for query using locally hosted model."""
        try:
            result = self._embed_text(text)
            logger.info("[RAG] Query embedding generated, dim=%d", len(result))
            return result
        except Exception as e:
            logger.error("[RAG] Embedding generation failed: %s", e, exc_info=True)
            return []

    # ──────────────────────────────────────────────────────────────────
    # CRM form embeddings — auto-generate for new forms
    # ──────────────────────────────────────────────────────────────────

    def _get_embedding_path(self, form_filename: str) -> Path:
        """Get the embedding file path for a CRM form."""
        stem = Path(form_filename).stem
        return AGGREGATED_EMBEDDINGS_DIR / f"{stem}_embedding.json"

    def _ensure_crm_embeddings(self):
        """Check all submitted CRM forms and generate embeddings for any missing ones."""
        if not CRM_FORMS_DIR.exists():
            logger.warning("CRM forms directory not found: %s", CRM_FORMS_DIR)
            return

        new_count = 0
        for form_file in CRM_FORMS_DIR.glob("*.json"):
            embedding_path = self._get_embedding_path(form_file.name)
            if embedding_path.exists():
                continue

            try:
                form_data = json.loads(form_file.read_text(encoding="utf-8"))
                text = _crm_form_to_text(form_data)
                if not text.strip():
                    continue

                embedding = self._embed_text(text)

                embedding_data = {
                    "text": text,
                    "embedding": embedding,
                    "source_file": form_file.name,
                    "metadata": {
                        "form_file": form_file.name,
                        "date_time": form_data.get("metadata", {}).get("date_time", ""),
                        "audio_file": form_data.get("metadata", {}).get("audio_file", ""),
                    },
                }
                embedding_path.write_text(json.dumps(embedding_data), encoding="utf-8")
                new_count += 1
                logger.info("[RAG] Generated embedding for: %s", form_file.name)
            except Exception as e:
                logger.error("[RAG] Failed to embed %s: %s", form_file.name, e)

        if new_count > 0:
            logger.info("[RAG] Generated %d new CRM form embeddings", new_count)
            self._embeddings_cache = None

    # ──────────────────────────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────────────────────────

    def _try_qdrant(self):
        """Get Qdrant client (embedded mode)."""
        if self._qdrant_available is False:
            return None
        if self._qdrant_client is not None:
            return self._qdrant_client

        try:
            from qdrant_client import QdrantClient

            qdrant_storage = os.getenv("QDRANT_STORAGE_PATH", str(REPO_ROOT / "qdrant_data"))
            os.makedirs(qdrant_storage, exist_ok=True)
            client = QdrantClient(path=qdrant_storage)
            self._qdrant_client = client
            self._qdrant_available = True
            logger.info("Using embedded Qdrant (storage: %s)", qdrant_storage)
            return client

        except Exception as e:
            logger.warning("Qdrant init failed: %s — will use file-based search", e)
            self._qdrant_available = False
            return None

    def _load_aggregated_embeddings(self) -> List[Dict[str, Any]]:
        """Load all CRM form embedding files. Cached for 60s."""
        import time
        now = time.time()
        if self._embeddings_cache is not None and (now - self._cache_time) < 60:
            return self._embeddings_cache

        self._ensure_crm_embeddings()

        all_chunks = []
        if not AGGREGATED_EMBEDDINGS_DIR.exists():
            return all_chunks

        for embedding_file in AGGREGATED_EMBEDDINGS_DIR.glob("*_embedding.json"):
            try:
                data = json.loads(embedding_file.read_text(encoding="utf-8"))
                if "embedding" in data and "text" in data:
                    all_chunks.append(data)
            except Exception:
                continue

        self._embeddings_cache = all_chunks
        self._cache_time = now
        logger.info("[RAG] Loaded %d aggregated CRM embeddings", len(all_chunks))
        return all_chunks

    def _search_local(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Cosine similarity search over CRM form embeddings."""
        chunks = self._load_aggregated_embeddings()
        if not chunks:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)

        scored = []
        for chunk in chunks:
            chunk_vec = np.array(chunk["embedding"], dtype=np.float32)
            if len(chunk_vec) != len(query_vec):
                continue
            score = _cosine_similarity(query_vec, chunk_vec)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, chunk in scored[:top_k]:
            metadata = chunk.get("metadata", {})
            results.append({
                "text": chunk["text"],
                "source_file": metadata.get("form_file", "unknown"),
                "date_time": metadata.get("date_time", ""),
                "audio_file": metadata.get("audio_file", ""),
                "similarity_score": score,
            })
        return results

    def _search_qdrant(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search Qdrant for similar documents."""
        client = self._try_qdrant()
        if client is None:
            return []

        try:
            collections = [c.name for c in client.get_collections().collections]
            if COLLECTION_NAME not in collections:
                return []

            results = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
            )
            docs = []
            for hit in results:
                doc = {
                    "text": hit.payload.get("text", ""),
                    "source_file": hit.payload.get("form_file", "unknown"),
                    "date_time": hit.payload.get("date_time", ""),
                    "audio_file": hit.payload.get("audio_file", ""),
                    "similarity_score": hit.score,
                }
                docs.append(doc)
            return docs
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            self._qdrant_available = False
            return []

    def _keyword_search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Keyword-based fallback when embedding search fails."""
        chunks = self._load_aggregated_embeddings()
        if not chunks:
            return []

        query_lower = query.lower()
        keywords = [w for w in query_lower.split() if len(w) > 2]
        if not keywords:
            return []

        scored = []
        for chunk in chunks:
            text_lower = chunk.get("text", "").lower()
            hits = sum(1 for kw in keywords if kw in text_lower)
            if hits > 0:
                scored.append((hits / len(keywords), chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            metadata = chunk.get("metadata", {})
            results.append({
                "text": chunk["text"],
                "source_file": metadata.get("form_file", "unknown"),
                "date_time": metadata.get("date_time", ""),
                "audio_file": metadata.get("audio_file", ""),
                "similarity_score": score,
            })
        return results

    def search_similar_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search CRM form embeddings. Qdrant → local cosine → keyword fallback."""
        logger.info("[RAG] Searching for: '%s'", query[:100])
        query_embedding = self._get_query_embedding(query)

        if query_embedding:
            results = self._search_qdrant(query_embedding, top_k)
            if results:
                logger.info("[RAG] Qdrant returned %d results", len(results))
                return results
            results = self._search_local(query_embedding, top_k)
            if results:
                logger.info("[RAG] Local cosine returned %d results", len(results))
                return results

        results = self._keyword_search(query, top_k)
        logger.info("[RAG] Keyword search returned %d results", len(results))
        return results

    # ──────────────────────────────────────────────────────────────────
    # Response generation
    # ──────────────────────────────────────────────────────────────────

    def generate_response(self, query: str, context_docs: List[Dict[str, Any]] = None) -> str:
        """Generate response using locally hosted Qwen LLM with retrieved context."""
        if context_docs is None:
            context_docs = self.search_similar_documents(query, top_k=5)

        if not context_docs:
            return "I couldn't find relevant information in the submitted CRM forms. Please ensure forms have been submitted and processed."

        context_text = "\n\n".join([
            f"[Form: {doc.get('source_file', 'unknown')} | Date: {doc.get('date_time', '')}]\n{doc['text']}"
            for doc in context_docs
        ])

        prompt = f"""You are an AI assistant for immigration advisory services. Answer the admin's question based on the submitted CRM form data below.

Context from submitted CRM forms:
\"\"\"
{context_text}
\"\"\"

Admin's Question: {query}

Provide a concise, helpful answer based on the CRM form data. If the context doesn't contain enough information, say so clearly. Keep your answer under 200 words."""

        try:
            import torch
            tokenizer, model = self._load_llm()

            messages = [{"role": "user", "content": prompt}]
            try:
                inputs = tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                    enable_thinking=False,
                )
            except TypeError:
                inputs = tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                )

            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=512,
                    do_sample=False,
                    repetition_penalty=1.0,
                )
            generated_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
            response = tokenizer.decode(generated_tokens, skip_special_tokens=True)
            logger.info("[RAG] LLM response generated (%d chars)", len(response))
            return response.strip()
        except Exception as e:
            logger.error("[RAG] LLM generation failed: %s", e, exc_info=True)
            summary_parts = []
            for i, doc in enumerate(context_docs[:3], 1):
                text_snippet = doc["text"][:300].strip()
                summary_parts.append(f"{i}. [{doc.get('source_file', '?')}] {text_snippet}")
            return f"Based on relevant CRM forms found:\n\n" + "\n\n".join(summary_parts)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def invalidate_cache(self):
        """Clear the embeddings cache (call after new forms are submitted)."""
        self._embeddings_cache = None

    def query_sync(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Synchronous query — search + generate."""
        context_docs = self.search_similar_documents(query, top_k=top_k)
        response = self.generate_response(query, context_docs)
        return {"response": response, "context_docs": context_docs}

    async def query_async(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Async query — offloads heavy work to thread pool so event loop stays free."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_rag_executor, self.query_sync, query, top_k)
