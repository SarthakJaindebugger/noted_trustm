"""Shared configuration for speech_analysis_qa."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
AUDIO_DIR = BASE_DIR / "Lucy_audio_dialogues"
LEGACY_AUDIO_DIR = BASE_DIR.parent / "noted_s2t_pipeline" / "Lucy_audio_dialoges"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# User data layout used by the speech pipeline and backend.
USER_DATA_DIR = REPO_ROOT / "knowledgebase" / "users_admin_data" / "users"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_AUDIO_SUBDIR = "recordings"
USER_TRANSCRIPTS_SUBDIR = "uploads"
USER_EMBEDDINGS_SUBDIR = "embedding"

# Pyannote / Whisper / Qwen settings
HF_TOKEN = os.environ.get("HF_TOKEN", "")
WHISPER_MODEL = "base"
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"

# Chunking defaults
CHUNK_MAX_WORDS = 120
CHUNK_OVERLAP_WORDS = 20
MERGE_GAP_SEC = 0.5

# Qdrant defaults
QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "speech_analysis_chunks"
QDRANT_DIMENSION = 4096
QDRANT_DISTANCE = "Cosine"

# RAG defaults
TOP_K = 5
MAX_CONTEXT_CHUNKS = 6

# Local storage
RAG_OUTPUT_DIR = OUTPUT_DIR / "rag_pipeline"
RAG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAG_PARQUET_PATH = RAG_OUTPUT_DIR / "rag_embeddings.parquet"
