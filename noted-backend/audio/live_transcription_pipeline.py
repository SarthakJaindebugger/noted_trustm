from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import numpy as np

from config import settings
from utils.audio_utils import convert_audio_format
from utils.text import strip_think_tags


logger = logging.getLogger(__name__)


class LiveTranscriptionPipeline:
    def __init__(
        self,
        *,
        batch_transcriber,
        chunker,
        live_sessions,
        openai_client,
        get_summary_model: Callable[[], str],
        generate_live_summary: Callable[[str], Any],
        persist_speaker_role_map: Callable[[str, Dict[str, str]], Awaitable[None]],
    ) -> None:
        self.batch_transcriber = batch_transcriber
        self.chunker = chunker
        self.live_sessions = live_sessions
        self.openai_client = openai_client
        self.get_summary_model = get_summary_model
        self.generate_live_summary = generate_live_summary
        self.persist_speaker_role_map = persist_speaker_role_map
        self.session_locks: Dict[str, threading.Lock] = {}

    async def process_chunk(
        self,
        session_id: str,
        audio_data,
        session_language: str = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            if session_id not in self.session_locks:
                self.session_locks[session_id] = threading.Lock()

            with self.session_locks[session_id]:
                audio_array = convert_audio_format(audio_data, target_sr=settings.audio.sample_rate)
                self.chunker.add_to_buffer(session_id, audio_array)

                if not self.chunker.should_process(session_id):
                    return None

                processing_chunk = self.chunker.get_processing_chunk(session_id)

            return await self._process_live_window(
                session_id,
                processing_chunk,
                session_language=session_language,
                force_finalize=False,
            )
        except Exception as exc:
            logger.error("Error processing chunk for session %s: %s", session_id, exc)
            return None

    async def flush_session(self, session_id: str, session_language: str = None) -> Optional[Dict[str, Any]]:
        if session_id not in self.session_locks:
            self.session_locks[session_id] = threading.Lock()

        with self.session_locks[session_id]:
            pending_audio = self.chunker.drain_pending_audio(session_id)

        return await self._process_live_window(
            session_id,
            pending_audio,
            session_language=session_language,
            force_finalize=True,
        )

    async def _process_live_window(
        self,
        session_id: str,
        new_audio: Optional[np.ndarray],
        *,
        session_language: str = None,
        force_finalize: bool = False,
    ) -> Optional[Dict[str, Any]]:
        del session_language  # reserved for future language forcing

        start_time = time.time()
        sample_rate = settings.audio.sample_rate
        rolling_window_seconds = float(getattr(settings.audio, "live_diarization_window_seconds", 20.0) or 20.0)

        if new_audio is not None and len(new_audio) > 0:
            normalized_audio = self._normalize_audio(new_audio)
            self.live_sessions.append_live_audio(
                session_id,
                normalized_audio,
                sample_rate=sample_rate,
                window_seconds=rolling_window_seconds,
            )

        state = self.live_sessions.ensure_state(session_id)
        rolling_audio = state.rolling_audio
        if rolling_audio.size < int(sample_rate * 0.5):
            return None

        diarization_segments = await self.batch_transcriber.diarize_audio(
            rolling_audio,
            sample_rate=sample_rate,
            session_id=f"{session_id}:live",
        )
        if not diarization_segments:
            logger.info("Live diarization returned no segments for session %s", session_id)
            return None

        absolute_segments = [
            {
                **segment,
                "start": float(segment.get("start", 0.0) or 0.0) + float(state.rolling_start_time),
                "end": float(segment.get("end", 0.0) or 0.0) + float(state.rolling_start_time),
            }
            for segment in diarization_segments
        ]
        canonical_segments = self._stabilize_two_speaker_segments(session_id, absolute_segments)

        holdback_seconds = 0.0 if force_finalize else float(
            getattr(settings.audio, "live_diarization_holdback_seconds", 1.5) or 1.5
        )
        stable_cutoff = max(
            float(state.last_transcribed_end),
            float(state.rolling_end_time) - holdback_seconds,
        )
        finalized_turns = self._extract_finalized_turns(session_id, canonical_segments, stable_cutoff)
        if not finalized_turns:
            logger.debug(
                "No finalized live turns for session %s (force_finalize=%s, cutoff=%.2f)",
                session_id,
                force_finalize,
                stable_cutoff,
            )
            return None

        self.live_sessions.append_committed_diarization(session_id, finalized_turns)
        transcribed_segments = await self._transcribe_finalized_turns(session_id, finalized_turns)

        state = self.live_sessions.ensure_state(session_id)
        state.last_transcribed_end = max(
            float(state.last_transcribed_end),
            max(float(turn.get("end", 0.0) or 0.0) for turn in finalized_turns),
        )

        if not transcribed_segments:
            return None

        role_map = dict(state.speaker_role_map or {})
        if not role_map and state.speaker_role_attempts < 3:
            candidate_segments = list(state.segments) + transcribed_segments
            unique_speakers = {
                str(segment.get("speaker", "")).strip()
                for segment in candidate_segments
                if segment.get("speaker")
            }
            if len(unique_speakers) >= 2 and len(candidate_segments) >= 6:
                self.live_sessions.increment_role_attempts(session_id)
                detected_map = await self.classify_speaker_roles(candidate_segments, session_id)
                if detected_map:
                    self.live_sessions.apply_speaker_role_map(session_id, detected_map)
                    role_map = detected_map
                    await self.persist_speaker_role_map(session_id, detected_map)
                    logger.info("Speaker roles (live) for %s: %s", session_id, role_map)

        if role_map:
            transcribed_segments = [
                {**segment, "speaker": role_map.get(segment.get("speaker"), segment.get("speaker"))}
                for segment in transcribed_segments
            ]

        self.live_sessions.append_segments(session_id, transcribed_segments)
        conversation_entries = self.live_sessions.build_conversation_entries(transcribed_segments)
        text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in transcribed_segments
            if str(segment.get("text", "")).strip()
        ).strip()
        speakers = sorted({
            str(segment.get("speaker", "")).strip()
            for segment in transcribed_segments
            if str(segment.get("speaker", "")).strip()
        })

        result = {
            "text": text,
            "segments": transcribed_segments,
            "speakers": speakers or ["UNKNOWN"],
            "conversation_entries": conversation_entries,
            "processing_time": time.time() - start_time,
            "session_id": session_id,
            "timestamp": time.time(),
        }
        result["summary"] = self.live_sessions.maybe_refresh_live_summary(
            session_id,
            self.generate_live_summary,
        )

        logger.info(
            "Processed live window for %s in %.2fs (finalized_turns=%d, transcript_segments=%d, force_finalize=%s)",
            session_id,
            result["processing_time"],
            len(finalized_turns),
            len(transcribed_segments),
            force_finalize,
        )
        return result

    async def _transcribe_finalized_turns(
        self,
        session_id: str,
        finalized_turns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        sample_rate = settings.audio.sample_rate
        transcribed_segments: List[Dict[str, Any]] = []

        for turn in finalized_turns:
            turn_audio = self.live_sessions.slice_live_audio(
                session_id,
                float(turn.get("start", 0.0) or 0.0),
                float(turn.get("end", 0.0) or 0.0),
                sample_rate=sample_rate,
            )
            if turn_audio.size < int(sample_rate * 0.25):
                continue

            try:
                asr_payload = await self.batch_transcriber.transcribe_audio_span(
                    turn_audio,
                    sample_rate=sample_rate,
                )
            except Exception as exc:
                logger.warning(
                    "Live ASR failed for %s %.2f-%.2fs: %s",
                    turn.get("speaker", "speaker_00"),
                    float(turn.get("start", 0.0) or 0.0),
                    float(turn.get("end", 0.0) or 0.0),
                    exc,
                )
                continue

            text = str(asr_payload.get("text", "") or "").strip()
            if not text:
                continue

            transcribed_segments.append(
                {
                    "speaker": str(turn.get("speaker", "speaker_00")),
                    "text": text,
                    "start": float(turn.get("start", 0.0) or 0.0),
                    "end": float(turn.get("end", 0.0) or 0.0),
                    "confidence": 0.0,
                    "speaker_confidence": float(turn.get("confidence", 0.0) or 0.0),
                    "language": asr_payload.get("language"),
                }
            )

        return transcribed_segments

    def _stabilize_two_speaker_segments(
        self,
        session_id: str,
        absolute_segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged_segments = self._merge_adjacent_segments(absolute_segments)
        state = self.live_sessions.ensure_state(session_id)
        mapping = self._resolve_two_speaker_mapping(state, merged_segments)
        canonical_segments = [
            {
                **segment,
                "speaker": mapping.get(str(segment.get("speaker", "")).strip(), "speaker_00"),
            }
            for segment in merged_segments
        ]
        canonical_segments = self._merge_adjacent_segments(canonical_segments)
        self.live_sessions.set_window_diarization(session_id, mapping, canonical_segments)
        return canonical_segments

    def _resolve_two_speaker_mapping(
        self,
        state,
        segments: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        if not segments:
            return dict(state.current_window_mapping or {})

        duration_by_speaker: Dict[str, float] = {}
        for segment in segments:
            speaker = str(segment.get("speaker", "")).strip()
            duration = max(0.0, float(segment.get("end", 0.0) or 0.0) - float(segment.get("start", 0.0) or 0.0))
            duration_by_speaker[speaker] = duration_by_speaker.get(speaker, 0.0) + duration

        raw_speakers = [
            speaker
            for speaker, _ in sorted(duration_by_speaker.items(), key=lambda item: item[1], reverse=True)
            if speaker
        ]
        if not raw_speakers:
            return dict(state.current_window_mapping or {})

        if len(raw_speakers) == 1:
            raw = raw_speakers[0]
            if raw in state.current_window_mapping:
                return {raw: state.current_window_mapping[raw]}

            inferred = self._best_canonical_for_raw(raw, segments, state)
            if inferred:
                return {raw: inferred}

            if state.last_window_segments:
                return {raw: str(state.last_window_segments[-1].get("speaker", "speaker_00"))}
            return {raw: "speaker_00"}

        raw_a, raw_b = raw_speakers[:2]
        keep_mapping = {raw_a: "speaker_00", raw_b: "speaker_01"}
        swap_mapping = {raw_a: "speaker_01", raw_b: "speaker_00"}

        reference_segments = list(state.committed_diarization_segments or [])
        if state.last_window_segments:
            reference_segments.extend(state.last_window_segments)

        if not reference_segments:
            if raw_a in state.current_window_mapping and raw_b in state.current_window_mapping:
                return {
                    raw_a: state.current_window_mapping[raw_a],
                    raw_b: state.current_window_mapping[raw_b],
                }
            return keep_mapping

        keep_score = self._mapping_score(segments, keep_mapping, reference_segments)
        swap_score = self._mapping_score(segments, swap_mapping, reference_segments)

        if raw_a in state.current_window_mapping and raw_b in state.current_window_mapping:
            previous_mapping = {
                raw_a: state.current_window_mapping[raw_a],
                raw_b: state.current_window_mapping[raw_b],
            }
            previous_score = self._mapping_score(segments, previous_mapping, reference_segments)
        else:
            previous_mapping = {}
            previous_score = -1.0

        score_margin = 0.25
        if previous_mapping and abs(keep_score - swap_score) <= score_margin:
            if previous_score >= max(keep_score, swap_score) - score_margin:
                return previous_mapping

        return keep_mapping if keep_score >= swap_score else swap_mapping

    @staticmethod
    def _mapping_score(
        segments: List[Dict[str, Any]],
        mapping: Dict[str, str],
        reference_segments: List[Dict[str, Any]],
    ) -> float:
        score = 0.0
        for segment in segments:
            raw_speaker = str(segment.get("speaker", "")).strip()
            canonical_speaker = mapping.get(raw_speaker)
            if not canonical_speaker:
                continue

            start = float(segment.get("start", 0.0) or 0.0)
            end = float(segment.get("end", 0.0) or 0.0)
            for reference in reference_segments:
                if str(reference.get("speaker", "")).strip() != canonical_speaker:
                    continue
                overlap = min(end, float(reference.get("end", 0.0) or 0.0)) - max(
                    start,
                    float(reference.get("start", 0.0) or 0.0),
                )
                if overlap > 0:
                    score += overlap
        return score

    def _best_canonical_for_raw(
        self,
        raw_speaker: str,
        segments: List[Dict[str, Any]],
        state,
    ) -> Optional[str]:
        reference_segments = list(state.committed_diarization_segments or [])
        if state.last_window_segments:
            reference_segments.extend(state.last_window_segments)
        if not reference_segments:
            return None

        scores = {"speaker_00": 0.0, "speaker_01": 0.0}
        for segment in segments:
            if str(segment.get("speaker", "")).strip() != raw_speaker:
                continue
            start = float(segment.get("start", 0.0) or 0.0)
            end = float(segment.get("end", 0.0) or 0.0)
            for reference in reference_segments:
                canonical = str(reference.get("speaker", "")).strip()
                if canonical not in scores:
                    continue
                overlap = min(end, float(reference.get("end", 0.0) or 0.0)) - max(
                    start,
                    float(reference.get("start", 0.0) or 0.0),
                )
                if overlap > 0:
                    scores[canonical] += overlap

        if scores["speaker_00"] == scores["speaker_01"] == 0.0:
            return None
        return "speaker_00" if scores["speaker_00"] >= scores["speaker_01"] else "speaker_01"

    def _extract_finalized_turns(
        self,
        session_id: str,
        segments: List[Dict[str, Any]],
        stable_cutoff: float,
    ) -> List[Dict[str, Any]]:
        state = self.live_sessions.ensure_state(session_id)
        cursor = float(state.last_transcribed_end or 0.0)
        finalized: List[Dict[str, Any]] = []
        min_duration = max(0.35, float(getattr(settings.audio, "min_speech_duration", 0.1) or 0.1))

        for segment in self._merge_adjacent_segments(segments):
            segment_end = float(segment.get("end", 0.0) or 0.0)
            if segment_end <= cursor:
                continue
            if segment_end > stable_cutoff:
                continue

            start = max(cursor, float(segment.get("start", 0.0) or 0.0))
            end = segment_end
            if end - start < min_duration:
                continue

            finalized.append(
                {
                    **segment,
                    "start": start,
                    "end": end,
                }
            )
            cursor = end

        return finalized

    async def classify_speaker_roles(
        self,
        segments: List[Dict[str, Any]],
        session_id: str,
    ) -> Optional[Dict[str, str]]:
        if not segments:
            return None

        unique_speakers = sorted({segment.get("speaker", "") for segment in segments if segment.get("speaker")})
        if len(unique_speakers) < 2:
            return None

        excerpt_lines = []
        excerpt_char_budget = 900
        excerpt_chars = 0
        for segment in sorted(
            segments,
            key=lambda item: (
                float(item.get("start", 0.0) or 0.0),
                float(item.get("end", 0.0) or 0.0),
            ),
        ):
            if len(excerpt_lines) >= 12:
                break
            if float(segment.get("start", 0.0) or 0.0) >= 20.0:
                break
            speaker = segment.get("speaker", "unknown")
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            line = f"{speaker}: {text}"
            if excerpt_lines and (excerpt_chars + len(line)) > excerpt_char_budget:
                break
            excerpt_lines.append(line)
            excerpt_chars += len(line)

        if not excerpt_lines:
            return None

        excerpt = "\n".join(excerpt_lines)
        speakers_list = ", ".join(unique_speakers)
        prompt = (
            f"This is the beginning of a two-person service encounter. "
            f"Exactly one speaker is the Advisor and exactly one speaker is the Customer. "
            f"The speaker labels are: {speakers_list}.\n\n"
            f"Use only this early conversation excerpt (about the first 20 seconds) to determine who is who:\n"
            f"{excerpt}\n\n"
            f"Return ONLY a JSON object mapping the speaker labels to roles.\n"
            f"Example:\n"
            f'{{"speaker_00": "Advisor", "speaker_01": "Customer"}}\n'
            f"No explanation. No markdown. JSON only."
        )

        try:
            started_at = time.perf_counter()
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.get_summary_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=48,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            raw = strip_think_tags(response.choices[0].message.content or "")
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            role_map = json.loads(raw)
            if isinstance(role_map, dict) and all(value in ("Advisor", "Customer") for value in role_map.values()):
                logger.info(
                    "ROLE_CLASSIFY_TIMING session=%s elapsed_ms=%.1f excerpt_lines=%d excerpt_chars=%d",
                    session_id,
                    elapsed_ms,
                    len(excerpt_lines),
                    len(excerpt),
                )
                return role_map
            logger.warning("Invalid speaker role map for %s: %s", session_id, role_map)
            return None
        except Exception as exc:
            logger.error("Speaker classification failed for %s: %s", session_id, exc)
            return None

    def cleanup_session(self, session_id: str) -> None:
        self.chunker.cleanup_session(session_id)
        self.live_sessions.cleanup_session(session_id)
        self.session_locks.pop(session_id, None)

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        state = self.live_sessions.ensure_state(session_id)
        return {
            "buffer_size": self.chunker.get_buffer_size(session_id),
            "rolling_buffer_seconds": round(
                state.rolling_audio.size / float(settings.audio.sample_rate or 16000),
                2,
            ),
            "last_transcribed_end": float(state.last_transcribed_end or 0.0),
        }

    def iter_session_ids(self) -> List[str]:
        return list(self.session_locks.keys())

    @staticmethod
    def _normalize_audio(audio_chunk: np.ndarray) -> np.ndarray:
        if len(audio_chunk) == 0:
            return audio_chunk
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        max_val = np.abs(audio_chunk).max()
        if max_val > 0:
            audio_chunk = audio_chunk / max_val
        return audio_chunk

    @staticmethod
    def _merge_adjacent_segments(
        segments: List[Dict[str, Any]],
        gap_tolerance: float = 0.35,
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        ordered_segments = sorted(
            (
                {
                    **segment,
                    "start": float(segment.get("start", 0.0) or 0.0),
                    "end": float(segment.get("end", 0.0) or 0.0),
                    "speaker": str(segment.get("speaker", "speaker_00") or "speaker_00"),
                    "confidence": float(segment.get("confidence", 0.0) or 0.0),
                }
                for segment in segments
                if float(segment.get("end", 0.0) or 0.0) > float(segment.get("start", 0.0) or 0.0)
            ),
            key=lambda item: (item["start"], item["end"]),
        )

        for segment in ordered_segments:
            if merged:
                previous = merged[-1]
                if (
                    previous["speaker"] == segment["speaker"]
                    and segment["start"] - previous["end"] <= gap_tolerance
                ):
                    previous["end"] = max(previous["end"], segment["end"])
                    previous["confidence"] = max(previous.get("confidence", 0.0), segment.get("confidence", 0.0))
                    continue
            merged.append(segment)

        return merged
