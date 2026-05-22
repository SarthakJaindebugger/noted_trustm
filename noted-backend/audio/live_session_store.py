from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from config import settings
from models.summary_models import LiveSummary


logger = logging.getLogger(__name__)


@dataclass
class LiveConversationState:
    segments: List[Dict[str, Any]] = field(default_factory=list)
    full_text: str = ""
    last_summary: Optional[Dict[str, Any]] = None
    last_summary_ts: float = 0.0
    last_summary_length: int = 0
    chunks_since_summary: int = 0
    total_chunks: int = 0
    speaker_role_map: Dict[str, str] = field(default_factory=dict)
    speaker_role_attempts: int = 0
    final_summary: Optional[Dict[str, Any]] = None
    rolling_audio: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    rolling_start_time: float = 0.0
    rolling_end_time: float = 0.0
    last_transcribed_end: float = 0.0
    current_window_mapping: Dict[str, str] = field(default_factory=dict)
    last_window_segments: List[Dict[str, Any]] = field(default_factory=list)
    committed_diarization_segments: List[Dict[str, Any]] = field(default_factory=list)


class LiveSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, LiveConversationState] = {}

    def ensure_state(self, session_id: str) -> LiveConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = LiveConversationState()
        return self._sessions[session_id]

    def get_state(self, session_id: str) -> LiveConversationState:
        return self.ensure_state(session_id)

    def get_last_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.ensure_state(session_id).last_summary

    def get_final_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.ensure_state(session_id).final_summary

    def set_final_summary(self, session_id: str, summary: Dict[str, Any]) -> None:
        self.ensure_state(session_id).final_summary = summary

    def set_full_text(self, session_id: str, full_text: str) -> None:
        self.ensure_state(session_id).full_text = str(full_text or "").strip()

    def replace_transcript(
        self,
        session_id: str,
        segments: List[Dict[str, Any]],
        full_text: str,
    ) -> LiveConversationState:
        state = self.ensure_state(session_id)
        state.segments = list(segments)
        state.full_text = str(full_text or "").strip()
        return state

    def append_segments(self, session_id: str, segments: List[Dict[str, Any]]) -> LiveConversationState:
        state = self.ensure_state(session_id)
        state.segments.extend(segments)

        appended_text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if str(segment.get("text", "")).strip()
        )
        if appended_text:
            state.full_text = f"{state.full_text} {appended_text}".strip() if state.full_text else appended_text
        return state

    def append_live_audio(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: int,
        window_seconds: float,
    ) -> LiveConversationState:
        state = self.ensure_state(session_id)
        if audio_data is None or len(audio_data) == 0:
            return state

        audio = np.asarray(audio_data, dtype=np.float32)
        if state.rolling_audio.size == 0:
            state.rolling_audio = audio.copy()
        else:
            state.rolling_audio = np.concatenate([state.rolling_audio, audio])

        state.rolling_end_time += len(audio) / float(sample_rate or 16000)
        max_samples = max(1, int(float(window_seconds or 20.0) * float(sample_rate or 16000)))
        if state.rolling_audio.size > max_samples:
            overflow = state.rolling_audio.size - max_samples
            state.rolling_audio = state.rolling_audio[overflow:]
            state.rolling_start_time += overflow / float(sample_rate or 16000)

        state.rolling_start_time = max(0.0, state.rolling_end_time - (state.rolling_audio.size / float(sample_rate or 16000)))
        return state

    def slice_live_audio(
        self,
        session_id: str,
        start_time: float,
        end_time: float,
        sample_rate: int,
    ) -> np.ndarray:
        state = self.ensure_state(session_id)
        if state.rolling_audio.size == 0:
            return np.array([], dtype=np.float32)

        start_offset = max(0.0, float(start_time) - float(state.rolling_start_time))
        end_offset = max(start_offset, float(end_time) - float(state.rolling_start_time))
        start_idx = int(round(start_offset * float(sample_rate or 16000)))
        end_idx = int(round(end_offset * float(sample_rate or 16000)))
        start_idx = max(0, min(start_idx, state.rolling_audio.size))
        end_idx = max(start_idx, min(end_idx, state.rolling_audio.size))
        return state.rolling_audio[start_idx:end_idx].copy()

    def set_window_diarization(
        self,
        session_id: str,
        mapping: Dict[str, str],
        segments: List[Dict[str, Any]],
    ) -> LiveConversationState:
        state = self.ensure_state(session_id)
        state.current_window_mapping = dict(mapping or {})
        state.last_window_segments = list(segments or [])
        return state

    def append_committed_diarization(
        self,
        session_id: str,
        segments: List[Dict[str, Any]],
        keep_seconds: float = 120.0,
    ) -> LiveConversationState:
        state = self.ensure_state(session_id)
        if segments:
            state.committed_diarization_segments.extend(list(segments))
        cutoff = max(0.0, float(state.rolling_end_time) - float(keep_seconds or 120.0))
        state.committed_diarization_segments = [
            segment
            for segment in state.committed_diarization_segments
            if float(segment.get("end", 0.0) or 0.0) >= cutoff
        ]
        return state

    def apply_speaker_role_map(self, session_id: str, role_map: Dict[str, str]) -> LiveConversationState:
        state = self.ensure_state(session_id)
        state.speaker_role_map = dict(role_map or {})
        if not state.speaker_role_map:
            return state

        for segment in state.segments:
            original = segment.get("speaker")
            segment["speaker"] = state.speaker_role_map.get(original, original)
        return state

    def increment_role_attempts(self, session_id: str) -> int:
        state = self.ensure_state(session_id)
        state.speaker_role_attempts += 1
        return state.speaker_role_attempts

    def maybe_refresh_live_summary(
        self,
        session_id: str,
        summary_generator: Callable[[str], LiveSummary],
    ) -> Dict[str, Any]:
        state = self.ensure_state(session_id)
        state.total_chunks += 1
        state.chunks_since_summary += 1

        now = time.time()
        full_text = state.full_text

        should_refresh = False
        if not state.last_summary:
            should_refresh = bool(full_text.strip())
        else:
            has_new = len(full_text) > state.last_summary_length
            time_ok = (now - state.last_summary_ts) >= settings.summarization.live_refresh_seconds
            chunks_ok = state.chunks_since_summary >= settings.summarization.live_refresh_chunks
            should_refresh = has_new and (time_ok or chunks_ok)

        if should_refresh:
            try:
                live = summary_generator(full_text)
                payload = live.model_dump()
                state.last_summary = payload
                state.last_summary_ts = now
                state.last_summary_length = len(full_text)
                state.chunks_since_summary = 0
                return payload
            except Exception as exc:
                logger.error("Failed to refresh live summary: %s", exc)

        return state.last_summary or self.empty_live_summary().model_dump()

    def clear(self) -> None:
        self._sessions.clear()

    def cleanup_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @staticmethod
    def empty_live_summary() -> LiveSummary:
        return LiveSummary(
            current_summary="Waiting for conversation content...",
            topics_so_far=[],
            emerging_themes=[],
            potential_action_items=[],
            conversation_flow="Idle",
        )

    @staticmethod
    def empty_summary(error: str = "") -> Dict[str, Any]:
        safe_error = str(error or "").strip()
        if safe_error:
            safe_error = re.sub(r"<failed_attempts>[\s\S]*?</failed_attempts>", " ", safe_error, flags=re.IGNORECASE)
            safe_error = re.sub(r"<last_exception>[\s\S]*?</last_exception>", " ", safe_error, flags=re.IGNORECASE)
            safe_error = re.sub(r"\s+", " ", safe_error).strip()
            if len(safe_error) > 280:
                safe_error = safe_error[:280] + "..."
        return {
            "executive_summary": safe_error or "No conversation content available.",
            "customer_profile": "Unable to determine customer information",
            "topics_discussed": [],
            "customer_needs": [],
            "solutions_provided": [],
            "action_items": [],
            "key_decisions": [],
            "resources_mentioned": [],
            "outcome": "Session ended without recorded conversation",
            "follow_up_required": False,
            "participants": ["Customer", "Advisor"],
        }

    @staticmethod
    def build_conversation_entries(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for segment in segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue

            speaker = segment.get("speaker", "UNKNOWN")
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)

            if current and current["speaker"] == speaker and (start - current["end_time"]) < 5.0:
                current["text"] += " " + text
                current["end_time"] = end
            else:
                if current:
                    entries.append(current)
                current = {
                    "speaker": speaker,
                    "text": text,
                    "start_time": start,
                    "end_time": end,
                    "confidence": segment.get("confidence", 0.8),
                    "speaker_confidence": segment.get("speaker_confidence", 0.5),
                }

        if current:
            entries.append(current)
        return entries
