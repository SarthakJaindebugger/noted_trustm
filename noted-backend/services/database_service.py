from services.database_session_store import SessionStore, to_session_data
from services.database_summary_store import SummaryStore
from services.database_transcript_store import TranscriptStore


class DatabaseService:
    """Facade over focused database stores for session, transcript, and summary operations."""

    def __init__(self):
        self.sessions = SessionStore()
        self.transcripts = TranscriptStore()
        self.summaries = SummaryStore()

    @staticmethod
    def to_session_data(session):
        return to_session_data(session)

    async def create_session(self, db, session_data):
        return await self.sessions.create_session(db, session_data)

    async def get_session(self, db, session_id, owner_user_id=None):
        return await self.sessions.get_session(db, session_id, owner_user_id=owner_user_id)

    async def update_session(self, db, session_id, **kwargs):
        return await self.sessions.update_session(db, session_id, **kwargs)

    async def delete_session(self, db, session_identifier, owner_user_id=None):
        return await self.sessions.delete_session(db, session_identifier, owner_user_id=owner_user_id)

    async def list_sessions(self, db, active_only=True):
        return await self.sessions.list_sessions(db, active_only=active_only)

    async def add_transcript_entries(self, db, session_id, entries):
        return await self.transcripts.add_transcript_entries(db, session_id, entries)

    async def get_session_transcript(self, db, session_id):
        return await self.transcripts.get_session_transcript(db, session_id)

    async def delete_session_transcript(self, db, session_id):
        return await self.transcripts.delete_session_transcript(db, session_id)

    async def update_speakers(self, db, session_id, speakers_data):
        return await self.transcripts.update_speakers(db, session_id, speakers_data)

    async def remap_transcript_speakers(self, db, session_id, speaker_map):
        return await self.transcripts.remap_transcript_speakers(db, session_id, speaker_map)

    async def update_session_stats(self, db, session_id, stats_data):
        return await self.sessions.update_session_stats(db, session_id, stats_data)

    async def update_session_notes(self, db, session_id, notes):
        return await self.sessions.update_session_notes(db, session_id, notes)

    async def get_session_stats(self, db, session_id):
        return await self.sessions.get_session_stats(db, session_id)

    async def save_session_summary(self, db, session_id, summary_data):
        return await self.summaries.save_session_summary(db, session_id, summary_data)

    async def get_session_summary(self, db, session_id):
        return await self.summaries.get_session_summary(db, session_id)

    async def save_audio_chunk_info(self, db, session_id, chunk_data):
        return await self.transcripts.save_audio_chunk_info(db, session_id, chunk_data)

    async def cleanup_old_sessions(self, db, max_age_hours=24):
        return await self.sessions.cleanup_old_sessions(db, max_age_hours=max_age_hours)

    async def get_session_by_name(self, db, session_name, owner_user_id=None):
        return await self.sessions.get_session_by_name(db, session_name, owner_user_id=owner_user_id)

    async def update_session_by_name(self, db, session_name, **kwargs):
        return await self.sessions.update_session_by_name(db, session_name, **kwargs)

    async def rename_session(self, db, session_id, new_name):
        return await self.sessions.rename_session(db, session_id, new_name)

    async def get_active_sessions(self, db, owner_user_id=None):
        return await self.sessions.get_active_sessions(db, owner_user_id=owner_user_id)

    async def get_all_sessions(self, db, owner_user_id=None):
        return await self.sessions.get_all_sessions(db, owner_user_id=owner_user_id)

    async def get_session_by_websocket_id(self, db, websocket_session_id, owner_user_id=None):
        return await self.sessions.get_session_by_websocket_id(
            db,
            websocket_session_id,
            owner_user_id=owner_user_id,
        )

    async def update_session_status(self, db, session_db_id, status):
        return await self.sessions.update_session_status(db, session_db_id, status)

    async def add_transcript_entry(self, db, session_db_id, transcript_data, replace=False):
        return await self.transcripts.add_transcript_entry(
            db,
            session_db_id,
            transcript_data,
            replace=replace,
        )

    async def cleanup_expired_sessions(self, db, cutoff_time, owner_user_id=None):
        return await self.sessions.cleanup_expired_sessions(
            db,
            cutoff_time,
            owner_user_id=owner_user_id,
        )

    async def get_highest_session_number(self, db):
        return await self.sessions.get_highest_session_number(db)

    async def session_name_exists(self, db, session_name):
        return await self.sessions.session_name_exists(db, session_name)
