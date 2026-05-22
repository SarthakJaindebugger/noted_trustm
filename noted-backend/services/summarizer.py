"""
SummarizerService — unified summarization with language auto-detection.

Two modes:
  - "live"  → LiveSummary (5 fields, fast, during recording)
  - "final" → ConversationSummary (13 fields, comprehensive customer handout)

Language is auto-detected from diarized segments (customer's language)
or can be specified manually. No separate translation endpoint needed.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from openai import OpenAI
import instructor

from config import settings, prompts
from models.summary_models import ConversationSummary, LiveSummary

logger = logging.getLogger(__name__)


class SummarizerService:
    """Single summarization service for both live and final modes."""

    def __init__(
        self,
        openai_client: Optional[OpenAI] = None,
        embedding_service: Any = None,
    ):
        if openai_client is None:
            openai_client = OpenAI(
                base_url=settings.models.generation.url,
                api_key=settings.models.generation.api_key or "none",
            )

        self.client = instructor.from_openai(openai_client)
        self.raw_client = openai_client
        self.model = settings.models.generation.name
        self.embedding_service = embedding_service

        logger.info("SummarizerService initialized (model=%s)", self.model)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def summarize(
        self,
        transcript: str,
        mode: str = "live",
        language: str = "en",
        segments: Optional[List[Dict]] = None,
        rag_context: str = "",
    ) -> Dict:
        """Generate a summary.

        Args:
            transcript: Full or partial transcript text.
            mode: "live" for in-progress summary, "final" for customer handout.
            language: Target language code (e.g., "en", "fi"). If "auto",
                      detects from diarized segments.
            segments: Diarized segments (used for language auto-detection).
            rag_context: Pre-built RAG context string for final summary.

        Returns:
            Summary as a dict.
        """
        if language == "auto" and segments:
            language = self.detect_customer_language(segments)

        if mode == "live":
            return self._live(transcript, language)
        else:
            return self._final(transcript, language, rag_context)

    # -----------------------------------------------------------------
    # Language detection
    # -----------------------------------------------------------------

    @staticmethod
    def detect_customer_language(segments: List[Dict]) -> str:
        """Detect the customer's language from diarized segments.

        Heuristic: the speaker with the most segments who is NOT the first
        speaker (advisor usually speaks first) is the customer.
        """
        if not segments:
            return "en"

        # Count segments per speaker
        speaker_counts: Counter = Counter()
        speaker_texts: Dict[str, List[str]] = {}
        for seg in segments:
            speaker = seg.get("speaker", "UNKNOWN")
            speaker_counts[speaker] += 1
            speaker_texts.setdefault(speaker, []).append(seg.get("text", ""))

        speakers = speaker_counts.most_common()
        if len(speakers) < 2:
            # Only one speaker, use their language
            return _detect_language_from_text(" ".join(speaker_texts.get(speakers[0][0], [])))

        # Assume advisor is the first speaker; customer is the other
        first_speaker = segments[0].get("speaker", "UNKNOWN")
        customer_speaker = None
        for sp, _ in speakers:
            if sp != first_speaker:
                customer_speaker = sp
                break

        if customer_speaker is None:
            customer_speaker = speakers[0][0]

        customer_text = " ".join(speaker_texts.get(customer_speaker, []))
        return _detect_language_from_text(customer_text)

    # -----------------------------------------------------------------
    # Private
    # -----------------------------------------------------------------

    def _live(self, transcript: str, language: str) -> Dict:
        """Generate a live (in-progress) summary."""
        if not transcript.strip():
            return LiveSummary(
                current_summary="Waiting for conversation content...",
                topics_so_far=[],
                emerging_themes=[],
                potential_action_items=[],
                conversation_flow="Idle",
            ).dict()

        try:
            summary = self.client.chat.completions.create(
                model=self.model,
                response_model=LiveSummary,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.render(
                            "live_summary.system",
                            language=language,
                            max_topics=settings.summarization.max_topics,
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompts.render("live_summary.user", transcript=transcript),
                    },
                ],
                temperature=0.2,
            )
            return summary.dict()
        except Exception as e:
            logger.error("Live summary failed: %s", e)
            return LiveSummary(
                current_summary="Summary generation in progress...",
                topics_so_far=[],
                emerging_themes=[],
                potential_action_items=[],
                conversation_flow="Processing",
            ).dict()

    def _final(self, transcript: str, language: str, rag_context: str = "") -> Dict:
        """Generate a comprehensive final summary (customer handout)."""
        if not transcript.strip():
            return _empty_summary()

        if not rag_context:
            rag_context = "No additional reference material available."

        try:
            summary = self.client.chat.completions.create(
                model=self.model,
                response_model=ConversationSummary,
                messages=[
                    {
                        "role": "system",
                        "content": prompts.render(
                            "final_summary.system",
                            language=language,
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompts.render(
                            "final_summary.user",
                            transcript=transcript,
                            rag_context=rag_context,
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=settings.models.generation.max_tokens,
            )
            return summary.model_dump()
        except Exception as e:
            logger.error("Final summary failed: %s", e)
            return _empty_summary(error=str(e))


# =====================================================================
# Helpers
# =====================================================================

def _detect_language_from_text(text: str) -> str:
    """Simple heuristic language detection from text content."""
    if not text:
        return "en"

    import re

    # Finnish markers
    finnish_markers = ["ä", "ö", "ja", "on", "ei", "hän", "minä", "sinä", "että", "kanssa"]
    # Swedish markers
    swedish_markers = ["å", "ä", "ö", "och", "att", "det", "för", "med", "jag"]
    # Arabic
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    # CJK
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"

    text_lower = text.lower()
    words = text_lower.split()

    fi_score = sum(1 for w in words if w in finnish_markers)
    sv_score = sum(1 for w in words if w in swedish_markers)

    if fi_score > len(words) * 0.05:
        return "fi"
    if sv_score > len(words) * 0.05:
        return "sv"

    return "en"


def _empty_summary(error: str = "") -> Dict:
    return {
        "executive_summary": error or "No conversation content available.",
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
