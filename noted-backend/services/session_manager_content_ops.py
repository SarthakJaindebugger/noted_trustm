import logging

from database.connection import AsyncSessionLocal
from services.transcript_support import (
    build_batch_transcript_entries,
    normalize_speaker_label,
    parse_json_transcript_blob,
    parse_structured_transcript_blob,
    transcript_model_from_entry,
)


logger = logging.getLogger(__name__)


async def _resolve_session(manager, session_identifier: str):
    session = await manager.get_session_by_name(session_identifier)
    if session:
        return session
    return await manager.get_session_by_db_id(session_identifier)


async def get_session_transcript(manager, session_identifier: str):
    try:
        session = await _resolve_session(manager, session_identifier)
        if not session:
            return []

        async with AsyncSessionLocal() as db:
            transcript_entries = await manager.db_service.get_session_transcript(db, session.db_id)
            if len(transcript_entries) == 1:
                entry = transcript_entries[0]
                parsed_entries = parse_structured_transcript_blob(entry)
                if parsed_entries:
                    return parsed_entries

                parsed_blob_entries = parse_json_transcript_blob(entry)
                if parsed_blob_entries:
                    return parsed_blob_entries

            return [transcript_model_from_entry(entry) for entry in transcript_entries]
    except Exception as exc:
        logger.error("Error getting transcript for %s: %s", session_identifier, exc)
        return []


async def add_transcript(manager, session_name: str, transcript_data: dict, replace: bool = False):
    try:
        session = await _resolve_session(manager, session_name)
        if not session:
            logger.warning("Cannot add transcript: session %s not found", session_name)
            return

        async with AsyncSessionLocal() as db:
            if replace:
                await manager.db_service.delete_session_transcript(db, session.db_id)
                replace = False

            if transcript_data.get("conversation_entries"):
                batch_entries = build_batch_transcript_entries(transcript_data)
                if batch_entries:
                    await manager.db_service.add_transcript_entries(db, session.db_id, batch_entries)
            else:
                single_entry = dict(transcript_data)
                single_entry["speaker"] = normalize_speaker_label(single_entry.get("speaker", "Unknown"))
                await manager.db_service.add_transcript_entry(
                    db,
                    session.db_id,
                    single_entry,
                    replace=replace,
                )
    except Exception as exc:
        logger.error("Error adding transcript to %s: %s", session_name, exc)


async def save_session_summary(manager, session_identifier: str, summary_data: dict):
    try:
        session = await _resolve_session(manager, session_identifier)
        if not session:
            logger.warning("Cannot save summary: session %s not found", session_identifier)
            return None

        async with AsyncSessionLocal() as db:
            return await manager.db_service.save_session_summary(db, session.db_id, summary_data)
    except Exception as exc:
        logger.error("Error saving summary for session %s: %s", session_identifier, exc)
        return None


async def remap_transcript_speakers(manager, session_identifier: str, speaker_map: dict) -> int:
    try:
        session = await _resolve_session(manager, session_identifier)
        if not session:
            logger.warning("Cannot remap transcript speakers: session %s not found", session_identifier)
            return 0

        async with AsyncSessionLocal() as db:
            return await manager.db_service.remap_transcript_speakers(db, session.db_id, speaker_map)
    except Exception as exc:
        logger.error("Error remapping transcript speakers for %s: %s", session_identifier, exc)
        return 0


async def get_session_summary_record(manager, session_identifier: str):
    try:
        session = await _resolve_session(manager, session_identifier)
        if not session:
            return None

        async with AsyncSessionLocal() as db:
            return await manager.db_service.get_session_summary(db, session.db_id)
    except Exception as exc:
        logger.error("Error getting summary for session %s: %s", session_identifier, exc)
        return None
