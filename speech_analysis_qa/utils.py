"""Utility helpers for speech_analysis_qa."""

import json
from pathlib import Path
from typing import Any, Dict, List, Union


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
