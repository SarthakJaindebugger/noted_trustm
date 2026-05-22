from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Optional

from config import prompts, settings
from models.summary_models import ConversationSummary
from utils.text import clean_transcript_text, format_transcript_for_prompt, strip_think_tags


logger = logging.getLogger(__name__)


class FinalSummaryPipeline:
    def __init__(
        self,
        *,
        openai_client,
        get_summary_model: Callable[[], str],
        create_summary_completion: Callable[..., Any],
        extract_json_payload: Callable[[Any], Optional[Any]],
        sanitize_summary_error: Callable[[Exception], str],
        live_sessions,
    ) -> None:
        self.openai_client = openai_client
        self.get_summary_model = get_summary_model
        self.create_summary_completion = create_summary_completion
        self.extract_json_payload = extract_json_payload
        self.sanitize_summary_error = sanitize_summary_error
        self.live_sessions = live_sessions

    @staticmethod
    def estimate_tokens_from_text(text: str) -> int:
        return max(1, math.ceil(len(text or "") / 4.0))

    def split_transcript_for_summary(
        self,
        transcript: str,
        target_tokens: int = 2048,
    ) -> List[str]:
        text = clean_transcript_text(transcript or "")
        if not text:
            return []

        target_chars = max(1200, int(target_tokens * 4))
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
        if not sentences:
            return [text]

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        def flush_current() -> None:
            nonlocal current, current_len
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0

        for sentence in sentences:
            if len(sentence) > target_chars:
                flush_current()
                words = sentence.split()
                piece: List[str] = []
                piece_len = 0
                for word in words:
                    word_len = len(word) + (1 if piece else 0)
                    if piece and piece_len + word_len > target_chars:
                        chunks.append(" ".join(piece).strip())
                        piece = [word]
                        piece_len = len(word)
                    else:
                        piece.append(word)
                        piece_len += word_len
                if piece:
                    chunks.append(" ".join(piece).strip())
                continue

            add_len = len(sentence) + (1 if current else 0)
            if current and current_len + add_len > target_chars:
                flush_current()
            current.append(sentence)
            current_len += add_len

        flush_current()
        return chunks or [text]

    def generate_chunk_note(self, chunk_text: str, language: str = "en") -> Dict[str, Any]:
        prompt = (
            "Summarize this transcript chunk as STRICT JSON with keys:\n"
            '{"summary": "...", "topics": ["..."], "needs": ["..."], '
            '"solutions": ["..."], "action_items": ["..."], "decisions": ["..."]}\n'
            "Rules:\n"
            "- Use only transcript facts.\n"
            "- Keep it concise.\n"
            "- If a list has no items, return [].\n"
            f"- Respond in {language}.\n\n"
            f"Transcript chunk:\n{chunk_text}"
        )
        response = self.openai_client.chat.completions.create(
            model=self.get_summary_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=min(700, settings.models.generation.max_tokens),
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = strip_think_tags(response.choices[0].message.content or "")
        payload = self.extract_json_payload(raw)
        if not isinstance(payload, dict):
            raise ValueError("Could not parse JSON chunk note")

        def normalize_list(value: Any) -> List[str]:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            return []

        return {
            "summary": str(payload.get("summary", "")).strip(),
            "topics": normalize_list(payload.get("topics")),
            "needs": normalize_list(payload.get("needs")),
            "solutions": normalize_list(payload.get("solutions")),
            "action_items": normalize_list(payload.get("action_items")),
            "decisions": normalize_list(payload.get("decisions")),
        }

    @staticmethod
    def dedupe_preserve(values: List[str], limit: int = 50) -> List[str]:
        seen = set()
        output: List[str] = []
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(value.strip())
            if len(output) >= limit:
                break
        return output

    def build_fallback_summary_from_notes(
        self,
        notes: List[Dict[str, Any]],
        error_message: str = "",
    ) -> Dict[str, Any]:
        summaries = self.dedupe_preserve([note.get("summary", "") for note in notes], limit=6)
        topics = self.dedupe_preserve([topic for note in notes for topic in note.get("topics", [])], limit=8)
        needs = self.dedupe_preserve([item for note in notes for item in note.get("needs", [])], limit=20)
        solutions = self.dedupe_preserve([item for note in notes for item in note.get("solutions", [])], limit=20)
        actions = self.dedupe_preserve([item for note in notes for item in note.get("action_items", [])], limit=20)
        decisions = self.dedupe_preserve([item for note in notes for item in note.get("decisions", [])], limit=20)

        topic_entries = []
        for topic in topics:
            topic_entries.append({
                "topic": topic,
                "key_points": [],
                "summary": "",
                "importance_level": "Medium",
                "action_items": [],
                "decisions_made": [],
            })

        executive_summary = " ".join(summaries[:3]).strip()
        if not executive_summary:
            executive_summary = (
                "Summary was generated from chunked transcript notes due an upstream connection issue."
            )

        return {
            "executive_summary": executive_summary,
            "customer_profile": "Profile could not be fully determined from fallback chunk summaries.",
            "topics_discussed": topic_entries,
            "customer_needs": needs,
            "solutions_provided": solutions,
            "action_items": [
                {"task": task, "responsible_party": None, "timeline": None, "priority": None}
                for task in actions
            ],
            "key_decisions": [
                {"decision": decision, "rationale": None, "impact": None}
                for decision in decisions
            ],
            "resources_mentioned": [],
            "outcome": error_message or "Session processed with chunked fallback summary flow.",
            "follow_up_required": bool(actions),
            "follow_up_details": None,
            "participants": ["Customer", "Advisor"],
        }

    def generate(
        self,
        session_id: str,
        language: str = "en",
        transcript_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        started_at = time.perf_counter()
        try:
            state = self.live_sessions.get_state(session_id)
            if transcript_text is not None:
                source_text = str(transcript_text or "").strip()
            else:
                source_text = format_transcript_for_prompt(state.segments)
                if not source_text:
                    source_text = clean_transcript_text(state.full_text)
            full_text = source_text.strip()

            if not full_text:
                return self.live_sessions.empty_summary()

            self.live_sessions.set_full_text(session_id, full_text)

            rag_context = "No additional reference material available."
            summary_schema_json = json.dumps(
                ConversationSummary.model_json_schema(),
                ensure_ascii=False,
            )
            transcript_tokens_est = self.estimate_tokens_from_text(full_text)
            long_transcript_threshold_tokens = 2048

            logger.info("Generating summary for session %s in %s", session_id, language)

            if transcript_tokens_est > long_transcript_threshold_tokens:
                chunks = self.split_transcript_for_summary(
                    full_text,
                    target_tokens=long_transcript_threshold_tokens,
                )
                logger.warning(
                    "SUMMARY_CHUNKING session=%s transcript_est_tokens=%d chunks=%d target_tokens=%d",
                    session_id,
                    transcript_tokens_est,
                    len(chunks),
                    long_transcript_threshold_tokens,
                )

                notes: List[Dict[str, Any]] = []
                for idx, chunk in enumerate(chunks, start=1):
                    try:
                        note = self.generate_chunk_note(chunk, language=language)
                        notes.append(note)
                    except Exception as chunk_error:
                        logger.warning(
                            "Chunk note generation failed for session %s chunk=%d/%d: %s",
                            session_id,
                            idx,
                            len(chunks),
                            chunk_error,
                        )
                        notes.append({
                            "summary": chunk[:700].strip(),
                            "topics": [],
                            "needs": [],
                            "solutions": [],
                            "action_items": [],
                            "decisions": [],
                        })

                reduced_text_parts: List[str] = []
                for idx, note in enumerate(notes, start=1):
                    reduced_text_parts.append(
                        (
                            f"[Chunk {idx}] Summary: {note.get('summary', '')}\n"
                            f"Topics: {', '.join(note.get('topics', []))}\n"
                            f"Needs: {', '.join(note.get('needs', []))}\n"
                            f"Solutions: {', '.join(note.get('solutions', []))}\n"
                            f"Action Items: {', '.join(note.get('action_items', []))}\n"
                            f"Decisions: {', '.join(note.get('decisions', []))}"
                        )
                    )
                reduced_text = "\n\n".join(reduced_text_parts)
                system_prompt = prompts.render("final_summary.system", language=language)
                user_prompt = prompts.render(
                    "final_summary.user",
                    transcript=reduced_text,
                    rag_context=rag_context,
                )
                prompt_chars = len(system_prompt) + len(user_prompt) + len(summary_schema_json)
                approx_prompt_tokens = prompt_chars // 4

                logger.warning(
                    "SUMMARY_PROMPT_DEBUG session=%s model=%s max_tokens=%s transcript_chars=%d system_chars=%d user_chars=%d schema_chars=%d approx_prompt_tokens=%d reduced=true",
                    session_id,
                    self.get_summary_model(),
                    settings.models.generation.max_tokens,
                    len(reduced_text),
                    len(system_prompt),
                    len(user_prompt),
                    len(summary_schema_json),
                    approx_prompt_tokens,
                )

                try:
                    final_summary = self.create_summary_completion(
                        response_model=ConversationSummary,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=settings.models.generation.max_tokens,
                    )
                    result = final_summary.model_dump()
                except Exception as reduce_error:
                    logger.error(
                        "Reduce-stage summary failed for session %s: %s",
                        session_id,
                        reduce_error,
                    )
                    result = self.build_fallback_summary_from_notes(
                        notes,
                        error_message=self.sanitize_summary_error(reduce_error),
                    )
            else:
                system_prompt = prompts.render("final_summary.system", language=language)
                user_prompt = prompts.render(
                    "final_summary.user",
                    transcript=full_text,
                    rag_context=rag_context,
                )
                prompt_chars = len(system_prompt) + len(user_prompt) + len(summary_schema_json)
                approx_prompt_tokens = prompt_chars // 4

                logger.warning(
                    "SUMMARY_PROMPT_DEBUG session=%s model=%s max_tokens=%s transcript_chars=%d system_chars=%d user_chars=%d schema_chars=%d approx_prompt_tokens=%d reduced=false",
                    session_id,
                    self.get_summary_model(),
                    settings.models.generation.max_tokens,
                    len(full_text),
                    len(system_prompt),
                    len(user_prompt),
                    len(summary_schema_json),
                    approx_prompt_tokens,
                )

                final_summary = self.create_summary_completion(
                    response_model=ConversationSummary,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=settings.models.generation.max_tokens,
                )
                result = final_summary.model_dump()

            self.live_sessions.set_final_summary(session_id, result)
            logger.info(
                "SUMMARY_TIMING session=%s language=%s total_ms=%.1f mode=%s transcript_est_tokens=%d",
                session_id,
                language,
                round((time.perf_counter() - started_at) * 1000.0, 1),
                "chunked" if transcript_tokens_est > long_transcript_threshold_tokens else "direct",
                transcript_tokens_est,
            )
            return result
        except Exception as exc:
            logger.info(
                "SUMMARY_TIMING session=%s language=%s total_ms=%.1f mode=error error=%s",
                session_id,
                language,
                round((time.perf_counter() - started_at) * 1000.0, 1),
                type(exc).__name__,
            )
            logger.error("Failed to generate summary for session %s: %s", session_id, exc)
            return self.live_sessions.empty_summary(error=self.sanitize_summary_error(exc))
