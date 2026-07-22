"""speech_analysis_qa package entry points."""

from .audio_to_transcript import SpeechTranscriber
from .embeddings import QwenEmbedder
from .transcript_chunking import speaker_aware_chunks, chunk_transcript_file
from .retrieval import QdrantStore
from .rag import RagPipeline
from .utils import (
    get_user_audio_dir,
    get_user_audio_path,
    get_user_base_dir,
    get_user_embedding_dir,
    get_user_embedding_path,
    get_user_transcript_dir,
    get_user_transcript_path,
    normalize_text,
    read_json,
    sanitize_username,
    timestamp_label,
    timestamped_filename,
    write_json,
)

__all__ = [
    "SpeechTranscriber",
    "QwenEmbedder",
    "speaker_aware_chunks",
    "chunk_transcript_file",
    "QdrantStore",
    "RagPipeline",
    "get_user_base_dir",
    "get_user_audio_dir",
    "get_user_audio_path",
    "get_user_transcript_dir",
    "get_user_transcript_path",
    "get_user_embedding_dir",
    "get_user_embedding_path",
    "sanitize_username",
    "timestamped_filename",
    "read_json",
    "write_json",
    "normalize_text",
    "timestamp_label",
]
