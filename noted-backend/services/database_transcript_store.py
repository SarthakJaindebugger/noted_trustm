import logging
from typing import Any, Dict, List

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AudioChunk, Speaker, TranscriptEntry


logger = logging.getLogger(__name__)


class TranscriptStore:
    async def add_transcript_entries(
        self,
        db: AsyncSession,
        session_id: str,
        entries: List[Dict[str, Any]],
    ) -> List[TranscriptEntry]:
        if not entries:
            return []

        created_entries: List[TranscriptEntry] = []
        try:
            for entry in entries:
                text = str(entry.get("text", "") or "").strip()
                if not text:
                    continue
                db_entry = TranscriptEntry(
                    session_id=session_id,
                    speaker=entry.get("speaker", "Speaker"),
                    text=text,
                    start_time=entry.get("start_time", 0.0),
                    end_time=entry.get("end_time", 0.0),
                    confidence=entry.get("confidence", 0.0),
                    speaker_confidence=entry.get("speaker_confidence", 0.0),
                    language=entry.get("language"),
                    tags=entry.get("tags", []),
                    chunk_index=entry.get("chunk_index", 0),
                )
                db.add(db_entry)
                created_entries.append(db_entry)

            if not created_entries:
                return []

            await db.commit()
            for entry in created_entries:
                await db.refresh(entry)
            return created_entries
        except Exception as exc:
            logger.error("Error adding transcript entries for session %s: %s", session_id, exc)
            await db.rollback()
            return []

    async def get_session_transcript(self, db: AsyncSession, session_id: str) -> List[TranscriptEntry]:
        try:
            result = await db.execute(
                select(TranscriptEntry)
                .where(TranscriptEntry.session_id == session_id)
                .order_by(TranscriptEntry.chunk_index, TranscriptEntry.start_time)
            )
            return result.scalars().all()
        except Exception as exc:
            logger.error("Error getting transcript for session %s: %s", session_id, exc)
            return []

    async def delete_session_transcript(self, db: AsyncSession, session_id: str) -> bool:
        try:
            await db.execute(
                delete(TranscriptEntry).where(TranscriptEntry.session_id == session_id)
            )
            await db.commit()
            return True
        except Exception as exc:
            logger.error("Error deleting transcript for session %s: %s", session_id, exc)
            await db.rollback()
            return False

    async def add_transcript_entry(
        self,
        db: AsyncSession,
        session_db_id: str,
        transcript_data: Dict[str, Any],
        replace: bool = False,
    ) -> bool:
        try:
            if replace:
                await db.execute(
                    delete(TranscriptEntry).where(TranscriptEntry.session_id == session_db_id)
                )
            created_entries = await self.add_transcript_entries(db, session_db_id, [transcript_data])
            if created_entries:
                logger.debug("Added transcript entry for session %s", session_db_id)
            return bool(created_entries)
        except Exception as exc:
            logger.error("Error adding/updating transcript entry: %s", exc)
            await db.rollback()
            return False

    async def update_speakers(self, db: AsyncSession, session_id: str, speakers_data: List[str]):
        try:
            existing_speakers = await db.execute(
                select(Speaker).where(Speaker.session_id == session_id)
            )
            existing_labels = {speaker.speaker_label for speaker in existing_speakers.scalars().all()}

            for speaker_label in speakers_data:
                if speaker_label not in existing_labels:
                    db.add(Speaker(session_id=session_id, speaker_label=speaker_label))

            await db.commit()
        except Exception as exc:
            logger.error("Error updating speakers for session %s: %s", session_id, exc)
            await db.rollback()

    async def remap_transcript_speakers(
        self,
        db: AsyncSession,
        session_id: str,
        speaker_map: Dict[str, str],
    ) -> int:
        updated_rows = 0
        try:
            for original_label, mapped_label in speaker_map.items():
                original = str(original_label or "").strip()
                mapped = str(mapped_label or "").strip()
                if not original or not mapped or original == mapped:
                    continue
                result = await db.execute(
                    update(TranscriptEntry)
                    .where(
                        TranscriptEntry.session_id == session_id,
                        TranscriptEntry.speaker == original,
                    )
                    .values(speaker=mapped)
                )
                updated_rows += int(result.rowcount or 0)

            await db.commit()
            return updated_rows
        except Exception as exc:
            logger.error("Error remapping transcript speakers for session %s: %s", session_id, exc)
            await db.rollback()
            return 0

    async def save_audio_chunk_info(self, db: AsyncSession, session_id: str, chunk_data: Dict[str, Any]) -> AudioChunk:
        try:
            chunk = AudioChunk(session_id=session_id, **chunk_data)
            db.add(chunk)
            await db.commit()
            await db.refresh(chunk)
            return chunk
        except Exception as exc:
            logger.error("Error saving audio chunk info: %s", exc)
            await db.rollback()
            raise
