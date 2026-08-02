"""
Batch speech transcription + diarization client.

Uses:
- vLLM OpenAI-compatible audio transcription endpoint for ASR
- a local Sortformer FastAPI service for speaker diarization
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional

import httpx
import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

_BRACKET_CONTENT_RE = re.compile(r"\[[^\]]*\]")
_ORPHAN_JSON_ARTIFACT_RE = re.compile(r'(?<!\w)[\[\]\{\}"]+(?!\w)')
_WHITESPACE_RE = re.compile(r"\s+")


class BatchSpeechTranscriber:
    """Transcribe diarized upload audio with a batch ASR endpoint and Sortformer."""

    def __init__(
        self,
        url: Optional[str] = None,
        model: Optional[str] = None,
        hotwords: Optional[str] = None,
        diarization_url: Optional[str] = None,
        diarization_model: Optional[str] = None,
    ):
        self.base_url = (url or settings.models.asr_batch.url or "").rstrip("/")
        self.model = model or settings.models.asr_batch.name
        self.hotwords = hotwords or settings.models.asr_batch.hotwords
        self.asr_concurrency = max(1, int(getattr(settings.models.asr_batch, "concurrency", 8) or 8))
        self.diarization_url = (diarization_url or settings.models.diarization.url or "").rstrip("/")
        self.diarization_model = diarization_model or settings.models.diarization.name
        self.diarization_max_speakers = max(1, int(getattr(settings.models.diarization, "max_speakers", 2) or 2))

        self.client = OpenAI(
            base_url=f"{self.base_url}/v1",
            api_key="none",
        )

        self._fallback_model_lock = None
        self._fallback_model_resolved = False

        logger.info(
            "Initialized BatchSpeechTranscriber: asr_url=%s asr_model=%s asr_concurrency=%d diar_url=%s diar_model=%s",
            self.base_url,
            self.model,
            self.asr_concurrency,
            self.diarization_url,
            self.diarization_model,
        )

    async def initialize(self):
        self._fallback_model_lock = asyncio.Lock()

    async def transcribe_full_recording(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        session_id: str = "",
        max_tokens_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        del max_tokens_override  # kept for compatibility with live pipeline calls

        if audio_data is None or len(audio_data) == 0:
            return self._empty_result()

        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        duration_seconds = len(audio_data) / float(sample_rate or 16000)
        logger.info(
            "Processing audio for session %s: %.1f seconds",
            session_id,
            duration_seconds,
        )

        transcribe_started_at = time.perf_counter()
        audio_bytes = self._encode_audio_wav_bytes(audio_data, sample_rate)

        diarization_started_at = time.perf_counter()
        diarization_segments = await self._run_diarization_request(audio_bytes, session_id=session_id)
        diarization_ms = round((time.perf_counter() - diarization_started_at) * 1000.0, 1)

        primary_asr_ms = 0.0
        turn_level_asr_ms = 0.0
        used_turn_level_asr = False
        asr_payload: Dict[str, Any] = {}
        merged_segments: List[Dict[str, Any]] = []

        if diarization_segments:
            used_turn_level_asr = True
            turn_level_started_at = time.perf_counter()
            merged_segments = await self._transcribe_diarized_turns(
                audio_data=audio_data,
                sample_rate=sample_rate,
                diarization_segments=diarization_segments,
            )
            turn_level_asr_ms = round((time.perf_counter() - turn_level_started_at) * 1000.0, 1)
        else:
            logger.warning(
                "Diarization unavailable for %s; falling back to single full-file ASR pass",
                session_id,
            )
            primary_asr_started_at = time.perf_counter()
            try:
                asr_payload = await self._run_transcription_with_model_fallback(audio_bytes)
            except Exception as e:
                logger.error("ASR request failed for session %s: %s", session_id, e)
                return self._empty_result(error=str(e))
            primary_asr_ms = round((time.perf_counter() - primary_asr_started_at) * 1000.0, 1)
            merged_segments = self._normalize_asr_segments(asr_payload, duration_seconds)

        if not merged_segments:
            return self._empty_result(error="Transcription returned no segments")

        merged_segments = self._strip_repetitions(merged_segments)

        speakers = sorted({segment["speaker"] for segment in merged_segments if segment.get("speaker")})
        full_text = " ".join(segment["text"] for segment in merged_segments if segment.get("text"))
        language = str(asr_payload.get("language") or "").strip().lower() or self._detect_language_heuristic(full_text)
        total_ms = round((time.perf_counter() - transcribe_started_at) * 1000.0, 1)
        timing_info = {
            "primary_asr_ms": primary_asr_ms,
            "diarization_ms": diarization_ms,
            "turn_level_asr_ms": turn_level_asr_ms,
            "total_ms": total_ms,
            "used_turn_level_asr": used_turn_level_asr,
            "diarization_segments": len(diarization_segments),
            "merged_segments": len(merged_segments),
        }
        logger.info(
            "TRANSCRIBE_TIMING session=%s audio_seconds=%.1f primary_asr_ms=%.1f diarization_ms=%.1f turn_level_asr_ms=%.1f total_ms=%.1f used_turn_level_asr=%s diarization_segments=%d merged_segments=%d",
            session_id,
            duration_seconds,
            primary_asr_ms,
            diarization_ms,
            turn_level_asr_ms,
            total_ms,
            used_turn_level_asr,
            len(diarization_segments),
            len(merged_segments),
        )

        return {
            "segments": merged_segments,
            "speakers": speakers,
            "full_text": full_text,
            "language": language or "unknown",
            "language_confidence": 0.8 if language else 0.0,
            "timings": timing_info,
        }

    async def _transcribe_diarized_turns(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        diarization_segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized_turns = self._prepare_diarization_turns(diarization_segments, sample_rate, len(audio_data))
        semaphore = asyncio.Semaphore(self.asr_concurrency)

        async def _transcribe_single_turn(turn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            start_time = float(turn["start"])
            end_time = float(turn["end"])
            start_idx = int(turn["start_idx"])
            end_idx = int(turn["end_idx"])
            duration = max(0.0, end_time - start_time)
            if end_idx <= start_idx or duration < 0.35:
                return None

            turn_audio = audio_data[start_idx:end_idx]
            turn_bytes = self._encode_audio_wav_bytes(turn_audio, sample_rate)

            try:
                async with semaphore:
                    turn_payload = await self._run_transcription_with_model_fallback(turn_bytes)
            except Exception as exc:
                logger.warning(
                    "Turn-level ASR failed for %s %.2f-%.2fs: %s",
                    turn.get("speaker", "speaker_00"),
                    start_time,
                    end_time,
                    exc,
                )
                return None

            turn_text = self._clean_segment_text(turn_payload.get("text", ""))
            if not turn_text:
                return None

            return {
                "speaker": str(turn.get("speaker", "speaker_00")),
                "text": turn_text,
                "start": start_time,
                "end": end_time,
                "confidence": 0.0,
                "speaker_confidence": float(turn.get("confidence", 0.0) or 0.0),
            }

        turn_results = await asyncio.gather(*(_transcribe_single_turn(turn) for turn in normalized_turns))
        transcribed = [turn for turn in turn_results if turn]
        transcribed.sort(key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0))))
        logger.info(
            "TURN_LEVEL_ASR turns=%d transcribed=%d concurrency=%d",
            len(normalized_turns),
            len(transcribed),
            self.asr_concurrency,
        )
        return transcribed

    async def _run_transcription_with_model_fallback(self, audio_bytes: bytes) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(self._run_transcription_request, audio_bytes)
        except Exception as exc:
            if not self._is_model_not_found_error(exc):
                raise
            async with self._fallback_model_lock:
                if not self._fallback_model_resolved:
                    fallback_model = await asyncio.to_thread(self._resolve_fallback_model)
                    if fallback_model and fallback_model != self.model:
                        logger.warning(
                            "ASR model '%s' not found; switching to served model '%s'",
                            self.model,
                            fallback_model,
                        )
                        self.model = fallback_model
                    self._fallback_model_resolved = True
            return await asyncio.to_thread(self._run_transcription_request, audio_bytes)

    async def transcribe_audio_span(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        if audio_data is None or len(audio_data) == 0:
            return self._empty_result(error="Empty audio span")

        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        audio_bytes = self._encode_audio_wav_bytes(audio_data, sample_rate)
        payload = await self._run_transcription_with_model_fallback(audio_bytes)
        if not isinstance(payload, dict):
            payload = {}

        text = self._clean_segment_text(payload.get("text", ""))
        language = str(payload.get("language") or "").strip().lower()
        return {
            "text": text,
            "language": language or self._detect_language_heuristic(text),
            "raw": payload,
        }

    async def diarize_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        session_id: str = "",
    ) -> List[Dict[str, Any]]:
        if audio_data is None or len(audio_data) == 0:
            return []

        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        audio_bytes = self._encode_audio_wav_bytes(audio_data, sample_rate)
        return await self._run_diarization_request(audio_bytes, session_id=session_id)

    def _run_transcription_request(self, audio_bytes: bytes) -> Dict[str, Any]:
        file_obj = io.BytesIO(audio_bytes)
        file_obj.name = "audio.wav"

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "file": file_obj,
            "response_format": "json",
            "temperature": 0.0,
        }
        if self.hotwords and self.hotwords.strip():
            kwargs["prompt"] = self.hotwords.strip()

        response = self.client.audio.transcriptions.create(**kwargs)
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if isinstance(response, dict):
            return response
        if hasattr(response, "__dict__"):
            return dict(response.__dict__)
        return json.loads(json.dumps(response))

    async def _run_diarization_request(self, audio_bytes: bytes, session_id: str) -> List[Dict[str, Any]]:
        if not self.diarization_url:
            return []

        request_data = {
            "session_id": session_id,
            "model": self.diarization_model,
            "max_speakers": str(self.diarization_max_speakers),
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.diarization_url}/diarize",
                    data=request_data,
                    files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Diarization request failed for %s: %s", session_id, exc)
            return []

        segments = payload.get("segments", []) if isinstance(payload, dict) else []
        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(segments):
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start", 0.0))
            except Exception:
                start = 0.0
            try:
                end = float(item.get("end", start))
            except Exception:
                end = start
            speaker = str(item.get("speaker", f"speaker_{index % max(1, self.diarization_max_speakers):02d}")).strip()
            if not speaker.startswith("speaker_"):
                match = re.search(r"(\d+)$", speaker)
                speaker = f"speaker_{int(match.group(1)):02d}" if match else f"speaker_{speaker}"
            confidence = float(item.get("confidence", 0.0) or 0.0)
            if end <= start:
                continue
            normalized.append({
                "start": start,
                "end": end,
                "speaker": speaker,
                "confidence": confidence,
            })

        return normalized

    @staticmethod
    def _normalize_asr_segments(payload: Dict[str, Any], duration_seconds: float) -> List[Dict[str, Any]]:
        text = BatchSpeechTranscriber._clean_segment_text(payload.get("text", ""))
        raw_segments = payload.get("segments") or []
        normalized: List[Dict[str, Any]] = []

        for raw in raw_segments:
            if not isinstance(raw, dict):
                continue
            segment_text = BatchSpeechTranscriber._clean_segment_text(raw.get("text", ""))
            if not segment_text:
                continue
            try:
                start = float(raw.get("start", 0.0))
            except Exception:
                start = 0.0
            try:
                end = float(raw.get("end", start))
            except Exception:
                end = start
            if end < start:
                end = start
            confidence = float(raw.get("avg_logprob", 0.0) or 0.0)
            normalized.append({
                "speaker": "speaker_00",
                "text": segment_text,
                "start": start,
                "end": end,
                "confidence": confidence,
                "speaker_confidence": 0.0,
            })

        if normalized:
            return normalized

        if not text:
            return []

        return [{
            "speaker": "speaker_00",
            "text": text,
            "start": 0.0,
            "end": max(0.0, duration_seconds),
            "confidence": 0.0,
            "speaker_confidence": 0.0,
        }]

    @staticmethod
    def _prepare_diarization_turns(
        diarization_segments: List[Dict[str, Any]],
        sample_rate: int,
        sample_count: int,
    ) -> List[Dict[str, Any]]:
        turns: List[Dict[str, Any]] = []
        sorted_segments = sorted(
            (
                {
                    "start": max(0.0, float(segment.get("start", 0.0) or 0.0)),
                    "end": max(0.0, float(segment.get("end", 0.0) or 0.0)),
                    "speaker": str(segment.get("speaker", "speaker_00") or "speaker_00"),
                    "confidence": float(segment.get("confidence", 0.0) or 0.0),
                }
                for segment in diarization_segments
                if float(segment.get("end", 0.0) or 0.0) > float(segment.get("start", 0.0) or 0.0)
            ),
            key=lambda item: (item["start"], item["end"]),
        )

        for segment in sorted_segments:
            start = segment["start"]
            end = segment["end"]
            start_idx = max(0, min(sample_count, int(math.floor(start * sample_rate))))
            end_idx = max(start_idx, min(sample_count, int(math.ceil(end * sample_rate))))
            if end_idx <= start_idx:
                continue

            current = {
                **segment,
                "start_idx": start_idx,
                "end_idx": end_idx,
            }

            if turns:
                previous = turns[-1]
                gap = start - float(previous["end"])
                if (
                    previous["speaker"] == current["speaker"]
                    and gap <= 0.35
                ):
                    previous["end"] = max(float(previous["end"]), end)
                    previous["end_idx"] = max(int(previous["end_idx"]), end_idx)
                    previous["confidence"] = max(float(previous.get("confidence", 0.0) or 0.0), current["confidence"])
                    continue

            turns.append(current)

        return turns

    @staticmethod
    def _strip_repetitions(segments: List[Dict[str, Any]], max_repeats: int = 1) -> List[Dict[str, Any]]:
        if len(segments) <= max_repeats:
            return segments

        cleaned: List[Dict[str, Any]] = []
        repeat_count = 0
        prev_text = None

        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if text == prev_text:
                repeat_count += 1
                if repeat_count >= max_repeats:
                    continue
            else:
                repeat_count = 0
                prev_text = text
            cleaned.append(seg)

        if len(cleaned) < len(segments):
            logger.warning(
                "Stripped %d hallucinated repetition segments (kept %d)",
                len(segments) - len(cleaned),
                len(cleaned),
            )
        return cleaned

    @staticmethod
    def _encode_audio_wav_bytes(audio_data: np.ndarray, sample_rate: int) -> bytes:
        buffer = io.BytesIO()
        if sf is not None:
            sf.write(buffer, audio_data, sample_rate, format="WAV", subtype="PCM_16")
        else:
            import scipy.io.wavfile

            audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            scipy.io.wavfile.write(buffer, sample_rate, audio_int16)
        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _detect_language_heuristic(text: str) -> str:
        if not text:
            return "unknown"
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
        if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
            return "ja"
        if re.search(r"[\uac00-\ud7af]", text):
            return "ko"
        if re.search(r"[\u0600-\u06ff]", text):
            return "ar"
        if re.search(r"[\u0900-\u097f]", text):
            return "hi"
        return "en"

    @staticmethod
    def _empty_result(error: Optional[str] = None) -> Dict[str, Any]:
        return {
            "segments": [],
            "speakers": [],
            "full_text": "",
            "language": "unknown",
            "language_confidence": 0.0,
            "error": error or "",
        }

    @staticmethod
    def _is_model_not_found_error(error: Exception) -> bool:
        msg = str(error).lower()
        return "does not exist" in msg or "notfounderror" in msg or ("model" in msg and "404" in msg)

    @staticmethod
    def _clean_segment_text(text: str) -> str:
        value = str(text or "")
        value = _BRACKET_CONTENT_RE.sub(" ", value)
        value = _ORPHAN_JSON_ARTIFACT_RE.sub(" ", value)
        value = _WHITESPACE_RE.sub(" ", value).strip()
        return value

    def _resolve_fallback_model(self) -> Optional[str]:
        try:
            models = self.client.models.list()
            data = getattr(models, "data", None) or []
            if not data:
                return None
            return getattr(data[0], "id", None)
        except Exception as e:
            logger.warning("Could not resolve fallback ASR model ID: %s", e)
            return None
