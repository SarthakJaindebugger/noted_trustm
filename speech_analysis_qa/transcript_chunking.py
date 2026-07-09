"""Speaker-aware chunking and overlap logic."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Union

from .utils import normalize_text, chunks_from_sequence


@dataclass
class Chunk:
    chunk_id: int
    speaker: str
    start: float
    end: float
    text: str
    source_start: float
    source_end: float


def normalize_speaker_label(raw_speaker: str) -> str:
    speaker = str(raw_speaker or "").strip().upper().replace("-", "_").replace(" ", "_")
    if speaker.startswith("SPEAKER"):
        return speaker
    if speaker in {"ADVISOR", "ASSISTANT", "AGENT"}:
        return "ADVISOR"
    if speaker in {"CUSTOMER", "CLIENT", "USER"}:
        return "CUSTOMER"
    return speaker or "UNKNOWN"


def merge_adjacent_segments(segments: Sequence[dict], max_gap_sec: float = 0.5) -> List[dict]:
    merged = []
    for item in sorted(segments, key=lambda x: x.get("start", 0.0)):
        text = normalize_text(item.get("text", ""))
        if not text:
            continue
        speaker = normalize_speaker_label(item.get("speaker", "UNKNOWN"))
        start = float(item.get("start", 0.0))
        end = float(item.get("end", start))

        if merged and merged[-1]["speaker"] == speaker:
            gap = start - merged[-1]["end"]
            if gap <= max_gap_sec:
                merged[-1]["end"] = max(merged[-1]["end"], end)
                merged[-1]["text"] = f"{merged[-1]['text']} {text}".strip()
                continue

        merged.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return merged


def _estimate_word_timestamps(segment: dict, word_count: int, position: int) -> float:
    duration = max(segment["end"] - segment["start"], 0.0)
    return segment["start"] + duration * (position / max(word_count, 1))


def speaker_aware_chunks(
    segments: Sequence[dict],
    max_words: int = 120,
    overlap_words: int = 20,
    merge_gap_sec: float = 0.5,
) -> List[dict]:
    merged = merge_adjacent_segments(segments, max_gap_sec=max_gap_sec)
    chunks = []
    chunk_id = 0

    for segment in merged:
        words = normalize_text(segment["text"]).split()
        if not words:
            continue

        windows = chunks_from_sequence(words, max_words, overlap_words)
        for window in windows:
            window_start = window[0]
            window_end = window[-1]
            text = " ".join(window)
            start = _estimate_word_timestamps(segment, len(words), window_start)
            end = _estimate_word_timestamps(segment, len(words), window_end)
            chunks.append({
                "chunk_id": chunk_id,
                "speaker": segment["speaker"],
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "source_start": segment["start"],
                "source_end": segment["end"],
            })
            chunk_id += 1

    return chunks


def chunk_transcript_file(json_path: Union[str, Path], **kwargs) -> List[dict]:
    import json
    from pathlib import Path

    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Transcript JSON file not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict) and "segments" in data:
        segments = data["segments"]
    elif isinstance(data, list):
        segments = data
    else:
        raise ValueError("Transcript file must contain a list or a top-level 'segments' list")

    return speaker_aware_chunks(segments, **kwargs)
