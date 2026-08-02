"""
AudioProcessor — orchestrates the audio processing pipeline.

Live recording path:
    low-latency chunked ASR + diarization → transcript with speakers

Post-session path:
    Sortformer diarization + batch ASR turn transcription → transcript with speakers
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import numpy as np
from openai import OpenAI
import instructor

from config import settings, prompts
from audio.final_summary_pipeline import FinalSummaryPipeline
from audio.chunker import AudioChunker
from audio.live_session_store import LiveSessionStore
from audio.live_transcription_pipeline import LiveTranscriptionPipeline
from audio.transcription_service import BatchSpeechTranscriber
from models.summary_models import ConversationSummary, LiveSummary, ExperimentRender
from services.service_container import service_container

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self, enable_detailed_logging: bool = False):
        self.enable_detailed_logging = enable_detailed_logging

        # --- ASR + diarization ---
        self.batch_transcriber = None

        # Chunker (for buffering live audio before sending to ASR)
        self.chunker = AudioChunker()

        # Embedding service for RAG
        self.embedding_service = (
            service_container.get_embedding_service()
            or service_container.register_embedding_service()
        )

        # Threading for CPU-intensive tasks
        self.executor = ThreadPoolExecutor(max_workers=2)

        # Session state
        self.live_sessions = LiveSessionStore()

        # LLM client used for summary generation and structured outputs.
        llm_base_url = settings.models.generation.url
        llm_api_key = settings.models.generation.api_key or "none"
        self.summary_model = settings.models.generation.name

        self.openai_client = OpenAI(base_url=llm_base_url, api_key=llm_api_key)
        self.summary_client = instructor.from_openai(self.openai_client)
        self._sync_summary_model_with_server()
        self.final_summary_pipeline = FinalSummaryPipeline(
            openai_client=self.openai_client,
            get_summary_model=lambda: self.summary_model,
            create_summary_completion=self._create_summary_completion,
            extract_json_payload=self._extract_json_payload,
            sanitize_summary_error=self._sanitize_summary_error,
            live_sessions=self.live_sessions,
        )
        self.live_transcription_pipeline = LiveTranscriptionPipeline(
            batch_transcriber=self.batch_transcriber,
            chunker=self.chunker,
            live_sessions=self.live_sessions,
            openai_client=self.openai_client,
            get_summary_model=lambda: self.summary_model,
            generate_live_summary=self._generate_live_summary,
            persist_speaker_role_map=self._persist_speaker_role_map,
        )

        # Service catalog for RAG keyword matching
        self._service_catalog = self._load_service_catalog()

        logger.info(
            "AudioProcessor initialized (asr=%s, llm=%s)",
            settings.models.asr_batch.name,
            self.summary_model,
        )

    async def initialize(self):
        self.batch_transcriber = BatchSpeechTranscriber()
        await self.batch_transcriber.initialize()

    @staticmethod
    def _is_context_budget_error(error_text: str) -> bool:
        msg = (error_text or "").lower()
        if not msg:
            return False
        patterns = (
            "max_tokens must be at least 1",
            "maximum context length",
            "context length",
            "prompt is too long",
            "token budget",
        )
        return any(pattern in msg for pattern in patterns)

    async def _transcribe_chunk_with_fallback(
        self,
        session_id: str,
        chunk_audio: np.ndarray,
        sample_rate: int,
        offset_seconds: float,
        chunk_session_id: str,
        depth: int = 0,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Transcribe one chunk; auto-split only when context budget is exceeded."""
        asr_result = await self.batch_transcriber.transcribe_full_recording(
            chunk_audio, sample_rate, chunk_session_id
        )
        chunk_segments = asr_result.get("segments", []) or []
        if chunk_segments:
            merged: List[Dict[str, Any]] = []
            for seg in chunk_segments:
                seg_start = float(seg.get("start", 0.0))
                seg_end = float(seg.get("end", seg_start))
                merged.append({
                    **seg,
                    "start": offset_seconds + seg_start,
                    "end": offset_seconds + seg_end,
                })

            lang = str(asr_result.get("language", "")).strip().lower()
            languages = [lang] if lang and lang != "unknown" else []
            return merged, languages

        error_text = str(asr_result.get("error", "") or "")
        chunk_seconds = len(chunk_audio) / float(sample_rate or 16000)
        can_split = chunk_seconds > 8.0 and depth < 4
        if can_split and self._is_context_budget_error(error_text):
            mid = len(chunk_audio) // 2
            logger.warning(
                "Context budget hit for %s (chunk=%s, %.1fs). Splitting and retrying.",
                session_id,
                chunk_session_id,
                chunk_seconds,
            )
            left_segments, left_languages = await self._transcribe_chunk_with_fallback(
                session_id=session_id,
                chunk_audio=chunk_audio[:mid],
                sample_rate=sample_rate,
                offset_seconds=offset_seconds,
                chunk_session_id=f"{chunk_session_id}-a",
                depth=depth + 1,
            )
            right_segments, right_languages = await self._transcribe_chunk_with_fallback(
                session_id=session_id,
                chunk_audio=chunk_audio[mid:],
                sample_rate=sample_rate,
                offset_seconds=offset_seconds + (mid / float(sample_rate or 16000)),
                chunk_session_id=f"{chunk_session_id}-b",
                depth=depth + 1,
            )
            return left_segments + right_segments, left_languages + right_languages

        logger.warning(
            "No segments for session %s chunk=%s (offset=%.1fs, duration=%.1fs, error=%s)",
            session_id,
            chunk_session_id,
            offset_seconds,
            chunk_seconds,
            error_text or "none",
        )
        return [], []

    def _is_model_not_found_error(self, error: Exception) -> bool:
        msg = str(error).lower()
        return (
            "does not exist" in msg
            or "notfounderror" in msg
            or ("model" in msg and "404" in msg)
        )

    def _resolve_summary_fallback_model(self) -> Optional[str]:
        try:
            models = self.openai_client.models.list()
            data = getattr(models, "data", None) or []
            if not data:
                return None
            return getattr(data[0], "id", None)
        except Exception as e:
            logger.warning("Could not resolve fallback summary model ID: %s", e)
            return None

    def _sync_summary_model_with_server(self) -> None:
        try:
            models = self.openai_client.models.list()
            served_ids = [
                getattr(model_obj, "id", None)
                for model_obj in (getattr(models, "data", None) or [])
                if getattr(model_obj, "id", None)
            ]
        except Exception as e:
            logger.warning("Could not validate summary model against server models: %s", e)
            return

        if not served_ids or self.summary_model in served_ids:
            return

        fallback = served_ids[0]
        if fallback != self.summary_model:
            logger.warning(
                "Configured summary model '%s' not served. Falling back to '%s'.",
                self.summary_model,
                fallback,
            )
            self.summary_model = fallback

    @staticmethod
    def _is_tool_parser_error(error: Exception) -> bool:
        msg = str(error or "").lower()
        return (
            "--tool-call-parser" in msg
            or "requires --tool-call-parser" in msg
            or "tool_choice" in msg
        )

    @staticmethod
    def _is_incomplete_output_error(error: Exception) -> bool:
        msg = str(error or "").lower()
        if not msg:
            return False
        patterns = (
            "output is incomplete due to a max_tokens length limit",
            "finish_reason='length'",
            'finish_reason="length"',
            "<failed_attempts>",
            "<last_exception>",
        )
        return any(pattern in msg for pattern in patterns)

    @staticmethod
    def _sanitize_summary_error(error: Exception) -> str:
        msg = str(error or "").strip()
        if not msg:
            return "Summary generation failed."

        # Remove verbose internal debug payloads from user-facing fallback text.
        msg = re.sub(r"<failed_attempts>[\s\S]*?</failed_attempts>", " ", msg, flags=re.IGNORECASE)
        msg = re.sub(r"<last_exception>[\s\S]*?</last_exception>", " ", msg, flags=re.IGNORECASE)
        msg = re.sub(r"\s+", " ", msg).strip()

        lowered = msg.lower()
        if (
            "max_tokens length limit" in lowered
            or "finish_reason='length'" in lowered
            or 'finish_reason="length"' in lowered
        ):
            return "Summary generation hit the model output limit. Please retry."

        return (msg[:280] + "...") if len(msg) > 280 else msg

    @staticmethod
    def _extract_json_payload(raw_content: Any) -> Optional[Any]:
        if raw_content is None:
            return None

        if isinstance(raw_content, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw_content
            ).strip()
        else:
            text = str(raw_content).strip()

        if not text:
            return None

        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        start_obj = text.find("{")
        end_obj = text.rfind("}")
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            try:
                return json.loads(text[start_obj:end_obj + 1])
            except Exception:
                return None
        return None

    def _create_summary_completion_json_fallback(self, *, response_model: Any, **kwargs: Any) -> Any:
        schema = response_model.model_json_schema()
        schema_instruction = (
            "Return ONLY valid JSON that matches this schema. "
            "Do not include markdown fences, prose, or extra keys.\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=True)}"
        )
        messages = list(kwargs.get("messages", []))
        messages = [{"role": "system", "content": schema_instruction}] + messages

        request_kwargs: Dict[str, Any] = {
            "model": self.summary_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.0),
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
        if kwargs.get("max_tokens") is not None:
            request_kwargs["max_tokens"] = kwargs.get("max_tokens")

        from utils.text import strip_think_tags
        response = self.openai_client.chat.completions.create(**request_kwargs)
        content = strip_think_tags(response.choices[0].message.content or "") if response.choices else ""
        payload = self._extract_json_payload(content)
        if payload is None:
            raise ValueError("Could not parse JSON fallback response from summary model")
        return response_model.model_validate(payload)

    def _create_summary_completion(self, *, response_model: Any, **kwargs: Any) -> Any:
        # Disable Qwen3 thinking mode for clean JSON output
        kwargs.setdefault("extra_body", {})
        kwargs["extra_body"].setdefault("chat_template_kwargs", {})
        kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] = False

        if response_model is ConversationSummary and self.enable_detailed_logging:
            try:
                messages = kwargs.get("messages", [])
                debug_payload = {
                    "model": self.summary_model,
                    "temperature": kwargs.get("temperature"),
                    "max_tokens": kwargs.get("max_tokens"),
                    "extra_body": kwargs.get("extra_body", {}),
                    "message_count": len(messages),
                    "message_lengths": [
                        len(str(message.get("content", "")))
                        for message in messages
                        if isinstance(message, dict)
                    ],
                }
                logger.info(
                    "SUMMARY_REQUEST_PAYLOAD_START\n%s\nSUMMARY_REQUEST_PAYLOAD_END",
                    json.dumps(debug_payload, ensure_ascii=True),
                )
            except Exception as debug_error:
                logger.warning("Could not serialize summary request metadata for debug: %s", debug_error)

        try:
            return self.summary_client.chat.completions.create(
                model=self.summary_model,
                response_model=response_model,
                **kwargs,
            )
        except Exception as first_error:
            error_to_raise: Exception = first_error

            if self._is_model_not_found_error(first_error):
                fallback_model = self._resolve_summary_fallback_model()
                if fallback_model and fallback_model != self.summary_model:
                    logger.warning(
                        "Summary model '%s' not found; retrying with served model '%s'.",
                        self.summary_model,
                        fallback_model,
                    )
                    self.summary_model = fallback_model
                    try:
                        return self.summary_client.chat.completions.create(
                            model=self.summary_model,
                            response_model=response_model,
                            **kwargs,
                        )
                    except Exception as retry_error:
                        error_to_raise = retry_error

            if self._is_tool_parser_error(error_to_raise):
                logger.warning(
                    "Structured tool-calling unavailable for summary model '%s'; using JSON fallback.",
                    self.summary_model,
                )
                return self._create_summary_completion_json_fallback(
                    response_model=response_model,
                    **kwargs,
                )

            if self._is_incomplete_output_error(error_to_raise):
                logger.warning(
                    "Summary output truncated for model '%s'; retrying with JSON fallback.",
                    self.summary_model,
                )
                return self._create_summary_completion_json_fallback(
                    response_model=response_model,
                    **kwargs,
                )

            raise error_to_raise

    # =====================================================================
    # Live processing (during recording)
    # =====================================================================

    async def process_chunk(
        self, session_id: str, audio_data, session_language: str = None
    ) -> Optional[Dict]:
        return await self.live_transcription_pipeline.process_chunk(
            session_id,
            audio_data,
            session_language=session_language,
        )

    async def flush_live_session(
        self,
        session_id: str,
        session_language: str = None,
    ) -> Optional[Dict]:
        return await self.live_transcription_pipeline.flush_session(
            session_id,
            session_language=session_language,
        )

    # =====================================================================
    # Batch processing (post-session / file upload)
    # =====================================================================

    async def process_full_recording(
        self,
        session_id: str,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        chunk_duration: float = 600.0,
        progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Optional[Dict]:
        """Process an uploaded recording in fixed diarization/ASR chunks."""
        if audio_data is None or len(audio_data) == 0:
            logger.warning("No audio data for full processing of session %s", session_id)
            return None

        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        total_seconds = len(audio_data) / float(sample_rate or 16000)
        chunk_duration = max(15.0, float(chunk_duration or settings.audio.upload_chunk_duration or 300.0))
        chunk_samples = max(1, int(chunk_duration * float(sample_rate or 16000)))
        total_chunks = max(1, math.ceil(len(audio_data) / float(chunk_samples)))

        logger.info(
            "Processing full recording for %s in %d ASR chunks (total=%.1fs, chunk=%.1fs)",
            session_id,
            total_chunks,
            total_seconds,
            chunk_duration,
        )
        processing_started_at = time.perf_counter()
        if progress_callback:
            await progress_callback(0, total_chunks)

        segments: List[Dict[str, Any]] = []
        language_candidates: List[str] = []
        chunk_timings: List[Dict[str, Any]] = []

        for chunk_index in range(total_chunks):
            start_idx = chunk_index * chunk_samples
            end_idx = min(len(audio_data), start_idx + chunk_samples)
            chunk_audio = audio_data[start_idx:end_idx]
            if chunk_audio.size == 0:
                continue

            offset_seconds = start_idx / float(sample_rate or 16000)
            chunk_session_id = f"{session_id}#chunk-{chunk_index + 1}"
            chunk_started_at = time.perf_counter()
            chunk_segments, chunk_languages = await self._transcribe_chunk_with_fallback(
                session_id=session_id,
                chunk_audio=chunk_audio,
                sample_rate=sample_rate,
                offset_seconds=offset_seconds,
                chunk_session_id=chunk_session_id,
            )
            chunk_elapsed_ms = round((time.perf_counter() - chunk_started_at) * 1000.0, 1)
            chunk_timings.append({
                "chunk_index": chunk_index + 1,
                "elapsed_ms": chunk_elapsed_ms,
                "segments": len(chunk_segments),
                "duration_seconds": round(len(chunk_audio) / float(sample_rate or 16000), 2),
            })
            if chunk_segments:
                segments.extend(chunk_segments)
            if chunk_languages:
                language_candidates.extend(chunk_languages)

            if progress_callback:
                await progress_callback(chunk_index + 1, total_chunks)

        if not segments:
            logger.warning("No segments from ASR for session %s", session_id)
            return None

        segments.sort(key=lambda s: (float(s.get("start", 0.0)), float(s.get("end", 0.0))))

        # Filter out ASR noise: silence markers, human sounds, and model descriptions
        segments = self._filter_asr_noise(segments)
        if not segments:
            logger.warning("All segments were noise for session %s", session_id)
            return None

        language = "unknown"
        if language_candidates:
            language = Counter(language_candidates).most_common(1)[0][0]
        if not language or language == "unknown":
            language = "en"
        speakers_seen = {str(seg.get("speaker", "")).strip() for seg in segments if seg.get("speaker")}
        speakers = sorted(speakers_seen)

        # Classify speaker roles (Customer vs Advisor) using the LLM
        speaker_role_map = await self.live_transcription_pipeline.classify_speaker_roles(segments, session_id)
        if speaker_role_map:
            for seg in segments:
                original = seg.get("speaker", "")
                seg["speaker"] = speaker_role_map.get(original, original)
            speakers = sorted({seg["speaker"] for seg in segments})
            logger.info("Speaker roles for %s: %s", session_id, speaker_role_map)

        full_text = " ".join(
            str(seg.get("text", "")).strip()
            for seg in segments
            if str(seg.get("text", "")).strip()
        )

        # Store in conversation state for summarization
        self.live_sessions.replace_transcript(session_id, segments, full_text)

        # Build conversation entries (group consecutive same-speaker segments)
        conversation_entries = self.live_sessions.build_conversation_entries(segments)
        total_processing_ms = round((time.perf_counter() - processing_started_at) * 1000.0, 1)
        logger.info(
            "PROCESSING_TIMING session=%s audio_seconds=%.1f total_ms=%.1f chunks=%d transcript_segments=%d conversation_entries=%d chunk_timings=%s",
            session_id,
            total_seconds,
            total_processing_ms,
            total_chunks,
            len(segments),
            len(conversation_entries),
            chunk_timings,
        )

        return {
            "transcript": {
                "text": full_text,
                "segments": segments,
                "language": language,
                "language_confidence": 0.8,
            },
            "diarization": {"speakers": speakers, "segments": segments},
            "combined": {
                "text": full_text,
                "segments": segments,
                "speakers": speakers,
                "conversation_entries": conversation_entries,
            },
            "language": language,
            "language_confidence": 0.8,
            "full_text": full_text,
            "timings": {
                "processing_total_ms": total_processing_ms,
                "chunk_timings": chunk_timings,
            },
        }

    # Patterns that indicate ASR noise rather than actual speech
    _ASR_NOISE_PATTERNS = re.compile(
        r"^\[(?:Silence|Human Sounds?|Music|Noise|Laughter)\]$"
        r"|^This audio contains"
        r"|^The audio (?:is|contains|seems)"
        r"|not intelligible"
        r"|too poor to transcribe",
        re.IGNORECASE,
    )

    @classmethod
    def _filter_asr_noise(cls, segments: List[Dict]) -> List[Dict]:
        """Remove segments that are ASR noise markers or model descriptions, not actual speech."""
        return [
            seg for seg in segments
            if not cls._ASR_NOISE_PATTERNS.search(str(seg.get("text", "")).strip())
        ]

    def generate_final_summary(
        self,
        session_id: str,
        language: str = "en",
        transcript_text: Optional[str] = None,
    ) -> Dict:
        """Generate comprehensive final summary (customer handout)."""
        return self.final_summary_pipeline.generate(
            session_id,
            language=language,
            transcript_text=transcript_text,
        )

    def get_auto_summary(self, session_id: str) -> Optional[Dict]:
        return self.live_sessions.get_last_summary(session_id)

    # =====================================================================
    # Experiment output
    # =====================================================================

    def generate_experiment_output(
        self,
        transcript_text: str,
        ui_type: str,
        content_type: str,
        session_topics: Optional[List[str]] = None,
    ) -> Dict:
        """Generate custom experiment output from full transcript."""
        if not transcript_text or not transcript_text.strip():
            return {
                "ui_type": ui_type,
                "content_type": content_type,
                "title": "Transcript Not Available",
                "description": "No transcript data is available for this session yet.",
                "items": [],
                "diagram": None,
                "formatted_output": "",
            }

        experiment_section = prompts.get_section("experiment")
        content_prompts = experiment_section.get("content_types", {
            "action_points": "bullet-quality action points with responsible parties and timelines",
            "recap": "a narrative recap that highlights outcomes and decisions",
        })

        trimmed = transcript_text[-settings.rag.max_context_chars:]

        # RAG context
        topics = session_topics or self._extract_topic_candidates(trimmed)
        vector_documents = self._retrieve_vector_documents(topics, transcript=trimmed)
        keyword_matches = self._collect_service_keyword_matches(transcript_text)
        supporting_context = self._build_rag_context(vector_documents, keyword_matches)
        if not supporting_context:
            supporting_context = "No supporting knowledge base context was retrieved."
        elif len(supporting_context) > settings.rag.max_context_chars:
            supporting_context = supporting_context[: settings.rag.max_context_chars] + "\n..."

        safe_context = supporting_context.replace("{", "{{").replace("}", "}}")
        safe_transcript = trimmed.replace("{", "{{").replace("}", "}}")

        try:
            experiment_output = self._create_summary_completion(
                response_model=ExperimentRender,
                temperature=0.25,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.render("experiment.system"),
                    },
                    {
                        "role": "user",
                        "content": prompts.render(
                            "experiment.user",
                            content_focus=content_prompts.get(content_type, content_type.replace("_", " ")),
                            context=safe_context,
                            transcript=safe_transcript,
                        ),
                    },
                ],
            )
            payload = experiment_output.dict()
        except Exception as e:
            logger.error("Failed to generate experiment output: %s", e)
            return {
                "ui_type": ui_type,
                "content_type": content_type,
                "title": "Experiment Output",
                "description": "Could not generate AI content. Please try again.",
                "items": [],
                "diagram": None,
                "formatted_output": "",
            }

        payload["ui_type"] = ui_type
        payload["content_type"] = content_type
        payload["knowledge_context"] = {
            "topics": topics,
            "vector_matches": vector_documents,
            "keyword_matches": keyword_matches,
        }

        if not payload.get("formatted_output"):
            if ui_type == "list" and payload.get("items"):
                payload["formatted_output"] = "\n".join(f"- {item}" for item in payload["items"])
            elif ui_type == "diagram" and payload.get("diagram"):
                payload["formatted_output"] = payload["diagram"]
            else:
                parts = [payload.get("description", "")] + payload.get("items", [])
                payload["formatted_output"] = "\n\n".join(p for p in parts if p)

        return payload

    # =====================================================================
    # RAG helpers
    # =====================================================================

    @staticmethod
    def _tokenize_text(text: str) -> List[str]:
        return [t for t in re.findall(r"\b[\w\-]+\b", text.lower()) if len(t) > 2]

    def _load_service_catalog(self) -> List[Dict[str, Any]]:
        env_path = settings.rag.knowledgebase_csv_path
        candidate_paths = []
        if env_path:
            candidate_paths.append(Path(env_path))
        backend_root = Path(__file__).resolve().parents[1]
        candidate_paths.append(backend_root.parent / "knowledgebase" / "espoo_services.csv")
        candidate_paths.append(backend_root / "knowledgebase" / "espoo_services.csv")
        candidate_paths.append(backend_root.parent / "knowledgebase" / "suomi_services.csv")
        candidate_paths.append(backend_root / "knowledgebase" / "suomi_services.csv")

        csv_path: Optional[Path] = None
        for path in candidate_paths:
            if path.exists():
                csv_path = path
                break

        if csv_path is None:
            logger.warning("Service catalog CSV not found, keyword retrieval disabled")
            return []

        try:
            catalog: List[Dict[str, Any]] = []
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter=";"):
                    name = (row.get("Service Name") or "").strip()
                    if not name:
                        continue
                    normalized = name.lower()
                    catalog.append({
                        "service_name": name,
                        "normalized_name": normalized,
                        "token_set": set(self._tokenize_text(normalized)),
                        "description": (row.get("Description") or "").strip(),
                        "mini_description": (row.get("Mini Description") or "").strip(),
                        "short_description": (row.get("Short Description") or "").strip(),
                        "service_link": (row.get("Service Link") or "").strip(),
                        "other_links": (row.get("Other Links") or "").strip(),
                    })
            logger.info("Loaded %d services for keyword retrieval", len(catalog))
            return catalog
        except Exception as e:
            logger.warning("Failed to load service catalog: %s", e)
            return []

    def _collect_service_keyword_matches(
        self, transcript_text: str, limit: int = None
    ) -> List[Dict[str, Any]]:
        limit = limit or settings.rag.max_keyword_matches
        if not self._service_catalog or not transcript_text.strip():
            return []

        transcript_lower = transcript_text.lower()
        transcript_tokens = set(self._tokenize_text(transcript_text))
        matches: List[Dict[str, Any]] = []

        for entry in self._service_catalog:
            normalized = entry["normalized_name"]
            tokens = entry["token_set"]
            direct = normalized in transcript_lower
            ratio = len(tokens & transcript_tokens) / len(tokens) if tokens else 0.0

            if not direct and ratio < settings.rag.score_threshold:
                continue

            matches.append({
                "service_name": entry["service_name"],
                "service_link": entry.get("service_link", ""),
                "description": entry.get("mini_description", ""),
                "match_ratio": 1.0 if direct else ratio,
            })

        matches.sort(key=lambda m: m["match_ratio"], reverse=True)
        seen = set()
        unique = []
        for m in matches:
            if m["service_name"] not in seen:
                unique.append(m)
                seen.add(m["service_name"])
                if len(unique) >= limit:
                    break
        return unique

    def _extract_topic_candidates(
        self, transcript_text: str, max_topics: int = None
    ) -> List[str]:
        max_topics = max_topics or settings.summarization.max_topics
        if not transcript_text.strip():
            return []

        try:
            response = self.openai_client.chat.completions.create(
                model=self.summary_model,
                temperature=0.1,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.render("topic_extraction.system", max_topics=max_topics),
                    },
                    {
                        "role": "user",
                        "content": prompts.render("topic_extraction.user", transcript=transcript_text[-6000:]),
                    },
                ],
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            from utils.text import strip_think_tags
            content = strip_think_tags(response.choices[0].message.content or "")
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start: end + 1])
                else:
                    raise
            raw = data.get("topics", [])
        except Exception as e:
            logger.warning("Topic extraction failed: %s", e)
            raw = []

        topics = []
        for entry in raw:
            name = str(entry.get("topic") or entry.get("name") or entry if isinstance(entry, str) else "").strip()
            if name and name not in topics:
                topics.append(name)
            if len(topics) >= max_topics:
                break
        return topics

    def _retrieve_vector_documents(
        self,
        topics: List[str],
        transcript: str = "",
        limit_per_topic: int = None,
        score_threshold: float = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        limit_per_topic = limit_per_topic or settings.rag.max_vector_docs
        score_threshold = score_threshold or settings.rag.score_threshold
        if not topics or not self.embedding_service:
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}
        for topic in topics:
            try:
                points = self.embedding_service.search_knowledgebase(
                    topic + transcript, limit=limit_per_topic, score_threshold=score_threshold
                )
            except Exception as e:
                logger.warning("Vector search failed for '%s': %s", topic, e)
                continue

            docs = []
            for pt in points:
                payload = pt.payload or {}
                desc = (
                    payload.get("mini_description")
                    or payload.get("short_description")
                    or payload.get("description")
                    or ""
                )
                docs.append({
                    "service_name": payload.get("service_name"),
                    "description": desc,
                    "service_link": payload.get("service_link"),
                    "score": getattr(pt, "score", None),
                })
            if docs:
                result[topic] = docs
        return result

    def _build_rag_context(
        self,
        topic_documents: Dict[str, List[Dict[str, Any]]],
        keyword_matches: List[Dict[str, Any]],
    ) -> str:
        sections: List[str] = []

        for topic, docs in topic_documents.items():
            lines = []
            for doc in docs:
                name = doc.get("service_name") or "Unknown"
                desc = (doc.get("description") or "").strip()[:220]
                link = doc.get("service_link")
                line = f"- {name}"
                if link:
                    line += f" ({link})"
                if desc:
                    line += f": {desc}"
                lines.append(line)
            if lines:
                sections.append(f"Topic: {topic}\n" + "\n".join(lines))

        if keyword_matches:
            lines = []
            for m in keyword_matches:
                line = f"- {m['service_name']}"
                if m.get("service_link"):
                    line += f" ({m['service_link']})"
                desc = (m.get("description") or "").strip()[:200]
                if desc:
                    line += f": {desc}"
                lines.append(line)
            sections.append("Keyword matches\n" + "\n".join(lines))

        return "\n\n".join(sections)

    # =====================================================================
    async def _persist_speaker_role_map(self, session_id: str, role_map: Dict[str, str]) -> None:
        if not role_map:
            return

        session_manager = (
            service_container.get_session_manager()
            or service_container.register_session_manager()
        )
        updated_rows = await session_manager.remap_transcript_speakers(session_id, role_map)
        if updated_rows:
            logger.info("Persisted %d speaker remaps for %s", updated_rows, session_id)

    def _generate_live_summary(self, text: str) -> LiveSummary:
        if not text.strip():
            return self.live_sessions.empty_live_summary()

        try:
            return self._create_summary_completion(
                response_model=LiveSummary,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.render(
                            "live_summary.system",
                            language="en",
                            max_topics=settings.summarization.max_topics,
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompts.render("live_summary.user", transcript=text),
                    },
                ],
                temperature=0.2,
            )
        except Exception as e:
            logger.error("Live summary generation failed: %s", e)
            return self.live_sessions.empty_live_summary()

    # =====================================================================
    # Lifecycle
    # =====================================================================

    def cleanup_session(self, session_id: str) -> None:
        try:
            self.live_transcription_pipeline.cleanup_session(session_id)
            # Keep conversation state for post-session summarization
            logger.info("Cleaned up session %s", session_id)
        except Exception as e:
            logger.error("Error cleaning up session %s: %s", session_id, e)

    def get_session_stats(self, session_id: str) -> Dict:
        return self.live_transcription_pipeline.get_session_stats(session_id)

    async def shutdown(self) -> None:
        logger.info("Starting AudioProcessor shutdown...")
        try:
            for sid in self.live_transcription_pipeline.iter_session_ids():
                self.cleanup_session(sid)
            self.executor.shutdown(wait=True, timeout=10)
            self.live_sessions.clear()
            logger.info("AudioProcessor shutdown completed")
        except Exception as e:
            logger.error("Error during shutdown: %s", e)
            try:
                self.executor.shutdown(wait=False)
            except Exception:
                pass
