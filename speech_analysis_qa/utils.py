"""Utility helpers for speech_analysis_qa."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def read_json(path: Union[str, Path]) -> Any:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(data: Any, path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return path


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


def sanitize_username(username: str) -> str:
    safe = "".join(
        c if c.isalnum() or c in ("-", "_", ".") else "_"
        for c in str(username or "").strip()
    )
    return safe or "unknown"


def timestamped_filename(prefix: str, extension: str = "json", timestamp: Optional[datetime] = None) -> str:
    timestamp = timestamp or datetime.utcnow()
    sanitized_ext = extension.lstrip(".")
    label = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{label}.{sanitized_ext}"


def get_user_base_dir(username: str) -> Path:
    from .config import USER_DATA_DIR

    return USER_DATA_DIR / sanitize_username(username)


def get_user_audio_dir(username: str) -> Path:
    from .config import USER_AUDIO_SUBDIR

    return get_user_base_dir(username) / USER_AUDIO_SUBDIR


def get_user_transcript_dir(username: str) -> Path:
    from .config import USER_TRANSCRIPTS_SUBDIR

    return get_user_base_dir(username) / USER_TRANSCRIPTS_SUBDIR


def get_user_embedding_dir(username: str) -> Path:
    from .config import USER_EMBEDDINGS_SUBDIR

    return get_user_base_dir(username) / USER_EMBEDDINGS_SUBDIR


def ensure_user_data_dirs(username: str) -> Dict[str, Path]:
    dirs = {
        "base_dir": get_user_base_dir(username),
        "audio_dir": get_user_audio_dir(username),
        "transcript_dir": get_user_transcript_dir(username),
        "embedding_dir": get_user_embedding_dir(username),
    }
    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
    return dirs


def get_user_audio_path(username: str, timestamp: Optional[datetime] = None, extension: str = "wav") -> Path:
    path = get_user_audio_dir(username) / timestamped_filename("audio", extension, timestamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_user_transcript_path(username: str, timestamp: Optional[datetime] = None) -> Path:
    path = get_user_transcript_dir(username) / timestamped_filename("transcript", "json", timestamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_user_embedding_path(username: str, timestamp: Optional[datetime] = None, extension: str = "parquet") -> Path:
    path = get_user_embedding_dir(username) / timestamped_filename("embeddings", extension, timestamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_label(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(round(seconds % 60))
    return f"{mins:02d}:{secs:02d}"


def chunks_from_sequence(sequence: List[Any], size: int, overlap: int) -> List[List[Any]]:
    if size <= 0:
        raise ValueError("size must be > 0")
    step = max(1, size - overlap)
    items = []
    for start in range(0, len(sequence), step):
        end = min(start + size, len(sequence))
        items.append(sequence[start:end])
        if end == len(sequence):
            break
    return items
