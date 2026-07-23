"""speech_analysis_qa package entry points.

Imports are resolved lazily so lightweight pipeline CLIs can load path and
configuration helpers without importing optional ML runtimes such as torch.
"""

from importlib import import_module

_LAZY_EXPORTS = {
    "SpeechTranscriber": (".audio_to_transcript", "SpeechTranscriber"),
    "QwenEmbedder": (".embeddings", "QwenEmbedder"),
    "speaker_aware_chunks": (".transcript_chunking", "speaker_aware_chunks"),
    "chunk_transcript_file": (".transcript_chunking", "chunk_transcript_file"),
    "QdrantStore": (".retrieval", "QdrantStore"),
    "RagPipeline": (".rag", "RagPipeline"),
    "get_user_audio_dir": (".utils", "get_user_audio_dir"),
    "get_user_audio_path": (".utils", "get_user_audio_path"),
    "get_user_base_dir": (".utils", "get_user_base_dir"),
    "get_user_embedding_dir": (".utils", "get_user_embedding_dir"),
    "get_user_embedding_path": (".utils", "get_user_embedding_path"),
    "get_user_transcript_dir": (".utils", "get_user_transcript_dir"),
    "get_user_transcript_path": (".utils", "get_user_transcript_path"),
    "normalize_text": (".utils", "normalize_text"),
    "read_json": (".utils", "read_json"),
    "sanitize_username": (".utils", "sanitize_username"),
    "timestamp_label": (".utils", "timestamp_label"),
    "timestamped_filename": (".utils", "timestamped_filename"),
    "write_json": (".utils", "write_json"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
