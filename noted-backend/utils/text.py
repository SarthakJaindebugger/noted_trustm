"""
Shared text utilities — tokenization, text cleaning.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+")


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words (3+ chars)."""
    return [t for t in re.findall(r"\b[\w\-]+\b", text.lower()) if len(t) > 2]


def tokenize_unicode(text: str) -> List[str]:
    """Tokenize text preserving Unicode characters."""
    return [t.lower() for t in _WORD_RE.findall(text)]


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output (Qwen3 reasoning mode)."""
    if not text:
        return text
    return _THINK_RE.sub("", text).strip()


def clean_transcript_text(text: str) -> str:
    """Normalize transcript text for consistent UI + summarization behavior."""
    if not text:
        return ""

    cleaned = (
        str(text)
        .replace("<|endoftext|>", "")
    )
    cleaned = re.sub(r"<\|\d+\|>", "", cleaned)
    cleaned = re.sub(r"Please Repeat", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[Speaker \d+ \d+:\d+\]:\s*", "", cleaned)
    cleaned = re.sub(r"\[UNKNOWN \d+:\d+\]:\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def format_transcript_for_prompt(entries: Iterable[Any]) -> str:
    """Render transcript entries as speaker-labeled lines for summary prompts."""
    lines: List[str] = []
    for entry in entries or []:
        if isinstance(entry, dict):
            speaker = str(entry.get("speaker", "Unknown") or "Unknown").strip()
            text = clean_transcript_text(entry.get("text", ""))
        else:
            speaker = str(getattr(entry, "speaker", "Unknown") or "Unknown").strip()
            text = clean_transcript_text(getattr(entry, "text", ""))

        if not text:
            continue
        lines.append(f"{speaker}: {text}")

    return "\n".join(lines)
