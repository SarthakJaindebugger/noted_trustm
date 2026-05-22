from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Session, SessionStats
from models.session import SessionData, SessionStatus


logger = logging.getLogger(__name__)


def to_session_data(session: Session) -> SessionData:
    """Convert a database session row to the shared API/session model."""
    return SessionData(
        db_id=session.session_id,
        session_name=session.session_name,
        websocket_session_id=session.websocket_session_id,
        status=SessionStatus(session.status),
        created_at=session.created_at,
        updated_at=session.updated_at,
        owner_user_id=session.owner_user_id,
        owner_username=session.owner_username,
        client_name=session.client_name,
        advisor_name=session.advisor_name,
        service_type=session.service_type,
        advisor_notes=session.advisor_notes,
        total_duration=session.total_duration,
        speech_duration=session.speech_duration,
        processing_time=session.processing_time,
    )


class SessionStore:
    def _session_lookup_query(self, owner_user_id: Optional[str] = None):
        query = select(Session)
        if owner_user_id:
            query = query.where(Session.owner_user_id == owner_user_id)
        return query

    async def create_session(self, db: AsyncSession, session_data: SessionData) -> bool:
        """Create a new session in database."""
        try:
            status_value = session_data.status
            if isinstance(status_value, str):
                status_value = SessionStatus(status_value)

            db_session = Session(
                session_id=session_data.db_id,
                session_name=session_data.session_name,
                websocket_session_id=session_data.websocket_session_id,
                status=status_value.value,
                owner_user_id=session_data.owner_user_id,
                owner_username=session_data.owner_username,
                client_name=session_data.client_name,
                advisor_name=session_data.advisor_name,
                service_type=session_data.service_type,
                total_duration=session_data.total_duration,
                speech_duration=session_data.speech_duration,
                processing_time=session_data.processing_time,
            )
            db.add(db_session)
            db.add(SessionStats(session_id=session_data.db_id))
            await db.commit()
            logger.info("Created session in database: %s", session_data.db_id)
            return True
        except Exception as exc:
            logger.error("Error creating session in database: %s", exc)
            await db.rollback()
            return False

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        owner_user_id: Optional[str] = None,
    ) -> Optional[Session]:
        try:
            query = self._session_lookup_query(owner_user_id).where(Session.session_id == session_id)
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as exc:
            logger.error("Error getting session %s: %s", session_id, exc)
            return None

    async def update_session(self, db: AsyncSession, session_id: str, **kwargs) -> Optional[Session]:
        try:
            kwargs["updated_at"] = datetime.now()
            await db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(**kwargs)
            )
            await db.commit()
            return await self.get_session(db, session_id)
        except Exception as exc:
            logger.error("Error updating session %s: %s", session_id, exc)
            await db.rollback()
            return None

    async def delete_session(
        self,
        db: AsyncSession,
        session_identifier: str,
        owner_user_id: Optional[str] = None,
    ) -> bool:
        try:
            session_name_delete = delete(Session).where(Session.session_name == session_identifier)
            if owner_user_id:
                session_name_delete = session_name_delete.where(Session.owner_user_id == owner_user_id)
            result = await db.execute(session_name_delete)

            if result.rowcount == 0:
                session_id_delete = delete(Session).where(Session.session_id == session_identifier)
                if owner_user_id:
                    session_id_delete = session_id_delete.where(Session.owner_user_id == owner_user_id)
                result = await db.execute(session_id_delete)

            if result.rowcount == 0:
                await db.rollback()
                logger.info("Session not found for deletion: %s", session_identifier)
                return False

            await db.commit()
            logger.info("Deleted session: %s", session_identifier)
            return True
        except Exception as exc:
            logger.error("Error deleting session %s: %s", session_identifier, exc)
            await db.rollback()
            return False

    async def list_sessions(self, db: AsyncSession, active_only: bool = True) -> List[Session]:
        try:
            query = select(Session)
            if active_only:
                query = query.where(Session.status == "active")
            result = await db.execute(query.order_by(Session.updated_at.desc()))
            return result.scalars().all()
        except Exception as exc:
            logger.error("Error listing sessions: %s", exc)
            return []

    async def update_session_stats(self, db: AsyncSession, session_id: str, stats_data: Dict[str, Any]):
        try:
            await db.execute(
                update(SessionStats)
                .where(SessionStats.session_id == session_id)
                .values(**stats_data, updated_at=datetime.now())
            )
            await db.commit()
        except Exception as exc:
            logger.error("Error updating stats for session %s: %s", session_id, exc)
            await db.rollback()

    async def update_session_notes(self, db: AsyncSession, session_id: str, notes: str) -> bool:
        try:
            result = await db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(advisor_notes=notes, updated_at=datetime.now())
            )
            await db.commit()
            return result.rowcount > 0
        except Exception as exc:
            logger.error("Error updating notes for session %s: %s", session_id, exc)
            await db.rollback()
            return False

    async def get_session_stats(self, db: AsyncSession, session_id: str) -> Optional[SessionStats]:
        try:
            result = await db.execute(
                select(SessionStats).where(SessionStats.session_id == session_id)
            )
            return result.scalar_one_or_none()
        except Exception as exc:
            logger.error("Error getting stats for session %s: %s", session_id, exc)
            return None

    async def cleanup_old_sessions(self, db: AsyncSession, max_age_hours: int = 24) -> int:
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            result = await db.execute(
                select(Session).where(
                    Session.updated_at < cutoff_time,
                    Session.status != "active",
                )
            )
            old_sessions = result.scalars().all()
            for session in old_sessions:
                await db.execute(delete(Session).where(Session.session_id == session.session_id))
            await db.commit()
            logger.info("Cleaned up %s old sessions", len(old_sessions))
            return len(old_sessions)
        except Exception as exc:
            logger.error("Error cleaning up old sessions: %s", exc)
            await db.rollback()
            return 0

    async def get_session_by_name(
        self,
        db: AsyncSession,
        session_name: str,
        owner_user_id: Optional[str] = None,
    ) -> Optional[SessionData]:
        try:
            query = self._session_lookup_query(owner_user_id).where(Session.session_name == session_name)
            result = await db.execute(query)
            session = result.scalar_one_or_none()
            return to_session_data(session) if session else None
        except Exception as exc:
            logger.error("Error getting session by name %s: %s", session_name, exc)
            return None

    async def update_session_by_name(self, db: AsyncSession, session_name: str, **kwargs) -> Optional[SessionData]:
        try:
            kwargs["updated_at"] = datetime.now()
            await db.execute(
                update(Session)
                .where(Session.session_name == session_name)
                .values(**kwargs)
            )
            await db.commit()
            return await self.get_session_by_name(db, session_name)
        except Exception as exc:
            logger.error("Error updating session by name %s: %s", session_name, exc)
            await db.rollback()
            return None

    async def rename_session(self, db: AsyncSession, session_id: str, new_name: str) -> Optional[Session]:
        try:
            await db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(session_name=new_name, updated_at=datetime.now())
            )
            await db.commit()
            return await self.get_session(db, session_id)
        except IntegrityError as exc:
            logger.error("Integrity error renaming session %s: %s", session_id, exc)
            await db.rollback()
            raise
        except Exception as exc:
            logger.error("Error renaming session %s: %s", session_id, exc)
            await db.rollback()
            raise

    async def get_active_sessions(
        self,
        db: AsyncSession,
        owner_user_id: Optional[str] = None,
    ) -> List[SessionData]:
        try:
            query = self._session_lookup_query(owner_user_id).where(
                Session.status.in_(["active", "processing"])
            )
            result = await db.execute(query.order_by(Session.updated_at.desc()))
            return [to_session_data(session) for session in result.scalars().all()]
        except Exception as exc:
            logger.error("Error getting active sessions: %s", exc)
            return []

    async def get_all_sessions(
        self,
        db: AsyncSession,
        owner_user_id: Optional[str] = None,
    ) -> List[SessionData]:
        try:
            query = self._session_lookup_query(owner_user_id)
            result = await db.execute(query.order_by(Session.updated_at.desc()))
            return [to_session_data(session) for session in result.scalars().all()]
        except Exception as exc:
            logger.error("Error getting all sessions: %s", exc)
            return []

    async def get_session_by_websocket_id(
        self,
        db: AsyncSession,
        websocket_session_id: str,
        owner_user_id: Optional[str] = None,
    ) -> Optional[SessionData]:
        try:
            query = self._session_lookup_query(owner_user_id).where(
                Session.websocket_session_id == websocket_session_id
            )
            result = await db.execute(query)
            session = result.scalar_one_or_none()
            return to_session_data(session) if session else None
        except Exception as exc:
            logger.error("Error getting session by websocket_id %s: %s", websocket_session_id, exc)
            return None

    async def update_session_status(self, db: AsyncSession, session_db_id: str, status: SessionStatus) -> bool:
        try:
            await db.execute(
                update(Session)
                .where(Session.session_id == session_db_id)
                .values(status=status.value, updated_at=datetime.now())
            )
            await db.commit()
            return True
        except Exception as exc:
            logger.error("Error updating session status for %s: %s", session_db_id, exc)
            await db.rollback()
            return False

    async def cleanup_expired_sessions(
        self,
        db: AsyncSession,
        cutoff_time: datetime,
        owner_user_id: Optional[str] = None,
    ) -> int:
        try:
            query = self._session_lookup_query(owner_user_id).where(
                Session.updated_at < cutoff_time,
                Session.status != "active",
            )
            result = await db.execute(query)
            old_sessions = result.scalars().all()
            for session in old_sessions:
                await db.execute(delete(Session).where(Session.session_id == session.session_id))
            await db.commit()
            logger.info("Cleaned up %s expired sessions", len(old_sessions))
            return len(old_sessions)
        except Exception as exc:
            logger.error("Error cleaning up expired sessions: %s", exc)
            await db.rollback()
            return 0

    async def get_highest_session_number(self, db: AsyncSession) -> int:
        try:
            result = await db.execute(
                select(Session.session_name)
                .where(Session.session_name.like("SES-%"))
                .order_by(Session.session_name.desc())
            )
            highest_num = 0
            for name in result.scalars().all():
                if not name or not name.startswith("SES-"):
                    continue
                try:
                    highest_num = max(highest_num, int(name.split("-")[1]))
                except (IndexError, ValueError):
                    continue
            return highest_num
        except Exception as exc:
            logger.error("Error getting highest session number: %s", exc)
            return 0

    async def session_name_exists(self, db: AsyncSession, session_name: str) -> bool:
        try:
            result = await db.execute(
                select(Session.session_id).where(Session.session_name == session_name)
            )
            return result.scalar_one_or_none() is not None
        except Exception as exc:
            logger.error("Error checking if session name exists: %s", exc)
            return True
