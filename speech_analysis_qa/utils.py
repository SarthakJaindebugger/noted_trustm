# -*- coding: utf-8 -*-
"""Utility helpers used by speech_analysis_qa pipeline and package exports."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union


def sanitize_username(username: str) -> str:
    username = str(username or "").strip()
    username = username.replace(" ", "_")
    username = re.sub(r"[^A-Za-z0-9_.-]+", "_", username)
    username = username.strip("_.-")
    return username.lower() if username else "anonymous"


def write_json(obj: Any, path: Union[str, Path], indent: int = 2, ensure_ascii: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=ensure_ascii)


def read_json(path: Union[str, Path]) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def timestamp_label(seconds: float, include_hours: bool = False) -> str:
    total_seconds = max(0, int(round(seconds or 0)))
    mins, secs = divmod(total_seconds, 60)
    if include_hours or mins >= 60:
        hours, mins = divmod(mins, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def timestamped_filename(base: str, ext: Optional[str] = None) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(base or "file")).strip("_.-")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base}_{timestamp}"
    if ext:
        ext = f".{ext.lstrip('.')}"
        filename += ext
    return filename


def get_user_base_dir(users_root: Union[str, Path], username: str) -> Path:
    return Path(users_root) / sanitize_username(username)


def get_user_audio_dir(users_root: Union[str, Path], username: str) -> Path:
    return get_user_base_dir(users_root, username) / "recordings"


def get_user_audio_path(users_root: Union[str, Path], username: str, filename: str) -> Path:
    return get_user_audio_dir(users_root, username) / filename


def get_user_transcript_dir(users_root: Union[str, Path], username: str) -> Path:
    return get_user_base_dir(users_root, username) / "uploads"


def get_user_transcript_path(users_root: Union[str, Path], username: str, filename: str) -> Path:
    return get_user_transcript_dir(users_root, username) / filename


def get_user_embedding_dir(users_root: Union[str, Path], username: str) -> Path:
    return get_user_base_dir(users_root, username) / "embedding"


def get_user_embedding_path(users_root: Union[str, Path], username: str, filename: str) -> Path:
    return get_user_embedding_dir(users_root, username) / filename
