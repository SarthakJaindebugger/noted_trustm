# -*- coding: utf-8 -*-
"""
speech_analysis_qa/transcript_chunking.py
=========================================
Chunk a private transcript into text blocks for embedding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from speech_analysis_qa.speech_pipeline.common.config import CHUNK_SIZE, OVERLAP
from speech_analysis_qa.speech_pipeline.common.text_utils import chunk_text, segments_to_text


def _load_transcript(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "segments" in data:
        return data["segments"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported transcript format in {path}")


def chunk_transcript_file(path: str | Path) -> List[Dict[str, Any]]:
    segments = _load_transcript(path)
    text = segments_to_text(segments, with_timestamps=False).strip()
    if not text:
        return []

    chunks = chunk_text(text, CHUNK_SIZE, OVERLAP)
    return [{"text": chunk.strip()} for chunk in chunks if chunk.strip()]
