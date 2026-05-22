import json
import re
from datetime import datetime
from typing import Any, Dict, List

from models.transcript import TranscriptEntry


def normalize_speaker_label(raw_speaker: Any) -> str:
    speaker = str(raw_speaker or "").strip()
    if not speaker:
        return "Unknown"

    normalized = speaker.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"advisor", "assistant"}:
        return "Advisor"
    if normalized in {"customer", "client"}:
        return "Customer"
    if normalized == "0":
        return "speaker_00"
    if normalized == "1":
        return "speaker_01"

    if normalized.startswith("speaker_"):
        suffix = normalized.split("speaker_", 1)[1]
        if suffix.isdigit():
            return f"speaker_{int(suffix):02d}"

    return speaker


def transcript_model_from_entry(entry: Any) -> TranscriptEntry:
    timestamp = getattr(entry, "timestamp", None) or datetime.utcnow()
    return TranscriptEntry(
        session_id=str(getattr(entry, "session_id", "")),
        speaker=normalize_speaker_label(getattr(entry, "speaker", "Unknown")),
        text=str(getattr(entry, "text", "") or ""),
        start_time=float(getattr(entry, "start_time", 0.0) or 0.0),
        end_time=float(getattr(entry, "end_time", 0.0) or 0.0),
        confidence=float(getattr(entry, "confidence", 0.0) or 0.0),
        speaker_confidence=float(getattr(entry, "speaker_confidence", 0.0) or 0.0),
        timestamp=timestamp,
        language=getattr(entry, "language", None),
        tags=list(getattr(entry, "tags", []) or []),
    )


def parse_structured_transcript_blob(entry: Any) -> List[TranscriptEntry]:
    entry_text = str(getattr(entry, "text", "") or "")
    if "[" not in entry_text or "]:" not in entry_text:
        return []

    parsed_entries: List[TranscriptEntry] = []
    for line in entry_text.splitlines():
        line = line.strip()
        if not line or "[" not in line or "]:" not in line:
            continue

        bracket_end = line.find("]:")
        if bracket_end <= 0:
            continue

        header = line[1:bracket_end]
        content = line[bracket_end + 2:].strip()
        parts = header.rsplit(" ", 1)
        if len(parts) != 2 or not content:
            continue

        speaker = normalize_speaker_label(parts[0])
        timestamp_str = parts[1]
        try:
            minutes, seconds = timestamp_str.split(":")
            start_time = int(minutes) * 60 + int(seconds)
        except Exception:
            start_time = 0

        parsed_entries.append(
            TranscriptEntry(
                session_id=entry.session_id,
                speaker=speaker,
                text=content,
                start_time=start_time,
                end_time=start_time + 5,
                confidence=entry.confidence,
                speaker_confidence=entry.speaker_confidence,
                timestamp=entry.timestamp,
                language=entry.language,
                tags=entry.tags,
            )
        )

    return parsed_entries


def parse_json_transcript_blob(entry: Any) -> List[TranscriptEntry]:
    raw_text = str(getattr(entry, "text", "") or "").strip()
    if not raw_text:
        return []

    text = raw_text
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    payload: Any = None
    try:
        payload = json.loads(text)
    except Exception:
        object_candidates = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)
        recovered_items: List[Dict[str, Any]] = []
        for candidate in object_candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                recovered_items.append(parsed)
        if recovered_items:
            payload = recovered_items
        else:
            return []

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        maybe_items = payload.get("segments")
        items = maybe_items if isinstance(maybe_items, list) else []
    else:
        return []

    parsed_entries: List[TranscriptEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        content = item.get("Content", item.get("text", item.get("Text", "")))
        text_value = str(content or "").strip()
        if not text_value:
            continue

        try:
            start_time = float(item.get("Start", item.get("start", 0.0)))
        except Exception:
            start_time = 0.0
        try:
            end_time = float(item.get("End", item.get("end", start_time)))
        except Exception:
            end_time = start_time

        parsed_entries.append(
            TranscriptEntry(
                session_id=str(getattr(entry, "session_id", "")),
                speaker=normalize_speaker_label(item.get("Speaker", item.get("speaker", "Unknown"))),
                text=text_value,
                start_time=start_time,
                end_time=end_time,
                confidence=float(getattr(entry, "confidence", 0.0) or 0.0),
                speaker_confidence=float(getattr(entry, "speaker_confidence", 0.0) or 0.0),
                timestamp=getattr(entry, "timestamp", None) or datetime.utcnow(),
                language=getattr(entry, "language", None),
                tags=list(getattr(entry, "tags", []) or []),
            )
        )

    cleaned: List[TranscriptEntry] = []
    for item in parsed_entries:
        if cleaned and cleaned[-1].speaker == item.speaker and cleaned[-1].text.strip().lower() == item.text.strip().lower():
            continue
        cleaned.append(item)
    return cleaned


def build_batch_transcript_entries(transcript_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    conversation_entries = transcript_data.get("conversation_entries", []) or []
    batch_entries: List[Dict[str, Any]] = []

    for index, entry in enumerate(conversation_entries):
        text = str(entry.get("text", "") or "").strip()
        if not text:
            continue
        batch_entries.append(
            {
                "speaker": normalize_speaker_label(entry.get("speaker", "Unknown")),
                "text": text,
                "start_time": entry.get("start_time", 0),
                "end_time": entry.get("end_time", 0),
                "confidence": entry.get("confidence", transcript_data.get("confidence", 0.0)),
                "speaker_confidence": entry.get("speaker_confidence", 0.8),
                "language": transcript_data.get("language"),
                "tags": transcript_data.get("tags", []),
                "chunk_index": entry.get("chunk_index", index),
            }
        )

    return batch_entries
