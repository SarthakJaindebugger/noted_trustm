import asyncio
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from api.auth import AuthenticatedUser
from api.websocket_support import build_session_summary_payload, generate_topic_summary_payloads
from models.session import SessionData
from models.transcript import TranscriptEntry
from services.session_manager_async import AsyncSessionManager
from utils.text import format_transcript_for_prompt


def get_session_manager() -> AsyncSessionManager:
    from services.service_container import service_container

    return service_container.get_session_manager() or service_container.register_session_manager()


async def resolve_session_or_404(
    session_manager: AsyncSessionManager,
    session_identifier: str,
    current_user: AuthenticatedUser,
) -> SessionData:
    session = await session_manager.get_session_by_name(
        session_identifier,
        owner_user_id=current_user.id,
    )
    if not session:
        session = await session_manager.get_session_by_db_id(
            session_identifier,
            owner_user_id=current_user.id,
        )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def get_audio_processor() -> Tuple[Any, Any]:
    from api.websocket import manager

    if manager.audio_processor is None:
        manager.initialize_audio_processor()
    return manager.audio_processor, manager


async def get_transcript_entries_for_session(
    session_manager: AsyncSessionManager,
    session: SessionData,
) -> List[TranscriptEntry]:
    return await session_manager.get_session_transcript(session.db_id)


def transcript_entries_to_segments(transcript_entries: List[TranscriptEntry]) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for entry in transcript_entries:
        text = getattr(entry, "text", "") or ""
        if not text.strip():
            continue
        segments.append({
            "speaker": getattr(entry, "speaker", "Speaker"),
            "text": text.strip(),
            "start": float(getattr(entry, "start_time", 0.0) or 0.0),
            "end": float(getattr(entry, "end_time", 0.0) or 0.0),
        })
    return segments


def transcript_entries_to_text(transcript_entries: List[TranscriptEntry]) -> str:
    return "\n".join(
        entry.text
        for entry in transcript_entries
        if entry and getattr(entry, "text", "")
    )


def summary_record_to_response(session_id: str, summary_record) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "overview": summary_record.overview or "",
        "action_items": summary_record.action_items or [],
        "topics_discussed": summary_record.topics_discussed or [],
        "related_services": summary_record.related_services or [],
        "output_for": summary_record.output_for or (summary_record.topics_discussed or []),
        "confidence_score": summary_record.confidence_score or 0.0,
    }


async def generate_and_store_summary_for_session(
    session_manager: AsyncSessionManager,
    session_identifier: str,
    transcript_entries: Optional[List[TranscriptEntry]] = None,
    fallback_transcript_text: str = "",
):
    if transcript_entries is None:
        transcript_entries = await session_manager.get_session_transcript(session_identifier)

    summary_transcript = format_transcript_for_prompt(transcript_entries)
    if not summary_transcript:
        summary_transcript = fallback_transcript_text.strip()
    if not summary_transcript.strip():
        return None

    audio_processor, _ = get_audio_processor()
    loop = asyncio.get_running_loop()
    final_summary = await loop.run_in_executor(
        None,
        lambda: audio_processor.generate_final_summary(
            session_identifier,
            transcript_text=summary_transcript,
        ),
    )
    if not final_summary:
        return None

    topic_details = await generate_topic_summary_payloads(
        audio_processor,
        final_summary,
        transcript_text=summary_transcript,
    )
    summary_payload = build_session_summary_payload(audio_processor, final_summary, topic_details)
    await session_manager.save_session_summary(session_identifier, summary_payload)
    return summary_payload


async def get_or_generate_summary_record(
    session_manager: AsyncSessionManager,
    session: SessionData,
):
    stored_summary = await session_manager.get_session_summary_record(session.db_id)
    if stored_summary:
        return stored_summary

    transcript_entries = await get_transcript_entries_for_session(session_manager, session)
    generated = await generate_and_store_summary_for_session(
        session_manager,
        session.session_name,
        transcript_entries=transcript_entries,
    )
    if not generated:
        return None
    return await session_manager.get_session_summary_record(session.db_id)


def extract_session_topics(summary_record) -> List[str]:
    session_topics: List[str] = []
    if not summary_record:
        return session_topics

    raw_topics = summary_record.topics_discussed or []
    if isinstance(raw_topics, list):
        for entry in raw_topics:
            candidate = None
            if isinstance(entry, dict):
                candidate = entry.get("topic") or entry.get("name")
            elif entry:
                candidate = entry
            if candidate:
                text_value = str(candidate).strip()
                if text_value:
                    session_topics.append(text_value)

    if not session_topics:
        output_for = summary_record.output_for or []
        if isinstance(output_for, list):
            for item in output_for:
                text_value = str(item).strip()
                if text_value:
                    session_topics.append(text_value)
        elif output_for:
            text_value = str(output_for).strip()
            if text_value:
                session_topics.append(text_value)

    seen_topics = set()
    deduped_topics: List[str] = []
    for topic in session_topics:
        lowered = topic.lower()
        if lowered in seen_topics:
            continue
        seen_topics.add(lowered)
        deduped_topics.append(topic)
    return deduped_topics
