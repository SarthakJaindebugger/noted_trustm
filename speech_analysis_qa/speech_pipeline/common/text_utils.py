# -*- coding: utf-8 -*-
"""
common/text_utils.py
=====================
Small text/transcript helpers reused by stage 2, 3 and 4. Previously the
same "flatten segments into speaker: text lines" loop was copy-pasted in
pyannote_to_json.py and privacy_rag_2_outputs.py -- it now lives here once.
"""

from typing import List, Dict


def segments_to_text(segments: List[Dict], with_timestamps: bool = False) -> str:
    """Flatten a list of {"start", "end", "speaker", "text"} segments into
    one "SPEAKER: text" (or "[start-end] SPEAKER: text") block."""
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "").strip()
        if not text:
            continue
        if with_timestamps:
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
            lines.append(f"[{start:.2f}s - {end:.2f}s] {speaker}: {text}")
        else:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Fixed-size sliding-window chunking used for retrieval."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
        if start >= len(text):
            break
    return chunks


def format_seconds(seconds: float) -> str:
    """"125.4" -> "2 min 5 sec" -- used anywhere a human-readable duration
    is needed (visit duration, speaker totals, ...)."""
    seconds = max(0, int(round(seconds)))
    mins, secs = divmod(seconds, 60)
    return f"{mins} min {secs} sec"
