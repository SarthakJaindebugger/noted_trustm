from typing import Any, Dict, Optional
import asyncio
import logging

from models.session import SessionData, SessionStatus, SessionStats
from services.database_service import DatabaseService
from services import session_manager_content_ops, session_manager_session_ops

logger = logging.getLogger(__name__)


class AsyncSessionManager:
    """
    Async session manager with proper ID architecture:
    - db_id: Permanent UUID for database storage
    - session_name: Human-readable name (SES-00001) shown in frontend
    - websocket_session_id: Temporary UUID for WebSocket connections
    """

    def __init__(self):
        self.active_sessions: Dict[str, SessionData] = {}
        self.websocket_to_session: Dict[str, str] = {}
        self.processing_progress: Dict[str, Dict[str, Any]] = {}
        self.session_locks: Dict[str, asyncio.Lock] = {}
        self.db_service = DatabaseService()
        self._session_counter = 0
        self._counter_initialized = False

    def _apply_progress(self, session: SessionData) -> SessionData:
        return session_manager_session_ops.apply_progress(self, session)

    async def set_session_progress(
        self,
        session_name: str,
        percent: float,
        stage: Optional[str] = None,
        message: Optional[str] = None,
    ) -> bool:
        return await session_manager_session_ops.set_session_progress(
            self,
            session_name,
            percent,
            stage=stage,
            message=message,
        )

    async def get_session_progress(self, session_name: str) -> Optional[Dict[str, Any]]:
        return await session_manager_session_ops.get_session_progress(self, session_name)

    async def _initialize_counter(self):
        await session_manager_session_ops.initialize_counter(self)

    async def generate_session_name(self) -> str:
        return await session_manager_session_ops.generate_session_name(self)

    async def get_next_session_name(self) -> str:
        return await session_manager_session_ops.get_next_session_name(self)

    async def create_session(self, session_data: SessionData) -> SessionData:
        return await session_manager_session_ops.create_session(self, session_data)

    async def get_session_by_name(self, session_name: str, owner_user_id: Optional[str] = None) -> Optional[SessionData]:
        return await session_manager_session_ops.get_session_by_name(
            self,
            session_name,
            owner_user_id=owner_user_id,
        )

    async def get_session_by_websocket_id(
        self,
        websocket_session_id: str,
        owner_user_id: Optional[str] = None,
    ) -> Optional[SessionData]:
        return await session_manager_session_ops.get_session_by_websocket_id(
            self,
            websocket_session_id,
            owner_user_id=owner_user_id,
        )

    async def session_exists_by_name(self, session_name: str) -> bool:
        return await session_manager_session_ops.session_exists_by_name(self, session_name)

    async def session_exists(self, db_id: str, owner_user_id: Optional[str] = None) -> bool:
        return await session_manager_session_ops.session_exists(self, db_id, owner_user_id=owner_user_id)

    async def get_session_by_db_id(self, db_id: str, owner_user_id: Optional[str] = None) -> Optional[SessionData]:
        return await session_manager_session_ops.get_session_by_db_id(
            self,
            db_id,
            owner_user_id=owner_user_id,
        )

    async def update_session_notes(self, db_id: str, notes: str) -> bool:
        return await session_manager_session_ops.update_session_notes(self, db_id, notes)

    async def rename_session(self, session_identifier: str, new_name: str) -> Optional[SessionData]:
        return await session_manager_session_ops.rename_session(self, session_identifier, new_name)

    async def set_session_status(self, session_name: str, status: SessionStatus) -> bool:
        return await session_manager_session_ops.set_session_status(self, session_name, status)

    async def end_session(self, session_name: str) -> bool:
        return await session_manager_session_ops.end_session(self, session_name)

    async def pause_session(self, session_name: str) -> bool:
        return await session_manager_session_ops.pause_session(self, session_name)

    async def resume_session(self, session_name: str) -> bool:
        return await session_manager_session_ops.resume_session(self, session_name)

    async def get_session_transcript(self, session_identifier: str):
        return await session_manager_content_ops.get_session_transcript(self, session_identifier)

    async def add_transcript(self, session_name: str, transcript_data: Dict[str, Any], replace: bool = False):
        await session_manager_content_ops.add_transcript(self, session_name, transcript_data, replace=replace)

    async def save_session_summary(self, session_identifier: str, summary_data: Dict[str, Any]):
        return await session_manager_content_ops.save_session_summary(self, session_identifier, summary_data)

    async def remap_transcript_speakers(self, session_identifier: str, speaker_map: Dict[str, str]) -> int:
        return await session_manager_content_ops.remap_transcript_speakers(
            self,
            session_identifier,
            speaker_map,
        )

    async def get_session_summary_record(self, session_identifier: str):
        return await session_manager_content_ops.get_session_summary_record(self, session_identifier)

    async def get_session_stats(self, session_name: str, owner_user_id: Optional[str] = None) -> Optional[SessionStats]:
        return await session_manager_session_ops.get_session_stats(
            self,
            session_name,
            owner_user_id=owner_user_id,
        )

    async def list_active_sessions(self, owner_user_id: Optional[str] = None):
        return await session_manager_session_ops.list_active_sessions(self, owner_user_id=owner_user_id)

    async def get_all_sessions(self, owner_user_id: Optional[str] = None):
        return await session_manager_session_ops.get_all_sessions(self, owner_user_id=owner_user_id)

    async def cleanup_expired_sessions(
        self,
        max_age_hours: int = 24,
        owner_user_id: Optional[str] = None,
    ) -> int:
        return await session_manager_session_ops.cleanup_expired_sessions(
            self,
            max_age_hours=max_age_hours,
            owner_user_id=owner_user_id,
        )

    async def shutdown(self):
        await session_manager_session_ops.shutdown(self)
