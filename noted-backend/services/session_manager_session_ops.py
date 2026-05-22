import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError

from database.connection import AsyncSessionLocal
from models.session import SessionData, SessionStatus


logger = logging.getLogger(__name__)


def apply_progress(manager, session: SessionData) -> SessionData:
    progress = manager.processing_progress.get(session.session_name)
    if progress:
        session.processing_progress = float(progress.get("percent", 0.0))
        session.processing_stage = progress.get("stage")
        session.processing_message = progress.get("message")
    else:
        session.processing_progress = 0.0
        session.processing_stage = None
        session.processing_message = None
    return session


async def set_session_progress(
    manager,
    session_name: str,
    percent: float,
    stage: Optional[str] = None,
    message: Optional[str] = None,
) -> bool:
    session = await manager.get_session_by_name(session_name)
    if not session:
        return False

    bounded_percent = max(0.0, min(100.0, float(percent)))
    manager.processing_progress[session_name] = {
        "percent": bounded_percent,
        "stage": stage,
        "message": message,
        "updated_at": datetime.now(),
    }
    session.processing_progress = bounded_percent
    session.processing_stage = stage
    session.processing_message = message
    session.updated_at = datetime.now()
    return True


async def get_session_progress(manager, session_name: str):
    session = await manager.get_session_by_name(session_name)
    if not session:
        return None
    return {
        "session_name": session_name,
        "status": session.status.value if isinstance(session.status, SessionStatus) else str(session.status),
        "progress_percent": float(session.processing_progress or 0.0),
        "stage": session.processing_stage,
        "message": session.processing_message,
    }


async def initialize_counter(manager):
    if not manager._counter_initialized:
        async with AsyncSessionLocal() as db:
            manager._session_counter = await manager.db_service.get_highest_session_number(db)
            manager._counter_initialized = True
            logger.info("Initialized session counter to %s", manager._session_counter)


async def generate_session_name(manager) -> str:
    await initialize_counter(manager)
    max_retries = 100
    for _ in range(max_retries):
        manager._session_counter += 1
        candidate_name = f"SES-{manager._session_counter:05d}"
        async with AsyncSessionLocal() as db:
            if not await manager.db_service.session_name_exists(db, candidate_name):
                logger.info("Generated unique session name: %s", candidate_name)
                return candidate_name
        logger.warning("Session name %s already exists, trying next number", candidate_name)

    fallback_name = f"SES-{str(uuid.uuid4())[:8]}"
    logger.warning("Could not generate unique sequential name after %s attempts, using fallback: %s", max_retries, fallback_name)
    return fallback_name


async def get_next_session_name(manager) -> str:
    await initialize_counter(manager)
    next_counter = manager._session_counter + 1
    for _ in range(100):
        candidate_name = f"SES-{next_counter:05d}"
        async with AsyncSessionLocal() as db:
            if not await manager.db_service.session_name_exists(db, candidate_name):
                return candidate_name
        next_counter += 1
    return f"SES-{str(uuid.uuid4())[:8]}"


async def create_session(manager, session_data: SessionData) -> SessionData:
    session_name = session_data.session_name
    if session_name not in manager.session_locks:
        manager.session_locks[session_name] = asyncio.Lock()

    async with manager.session_locks[session_name]:
        if session_name in manager.active_sessions:
            existing_session = manager.active_sessions[session_name]
            logger.info("Session %s already exists, returning existing", session_name)
            return existing_session

        async with AsyncSessionLocal() as db:
            try:
                success = await manager.db_service.create_session(db, session_data)
                if not success:
                    raise Exception("Failed to create session in database")
            except IntegrityError as exc:
                if "UNIQUE constraint failed: sessions.session_name" not in str(exc):
                    raise
                logger.warning("Session name collision for %s, generating new name", session_name)
                new_session_name = await generate_session_name(manager)
                session_data.session_name = new_session_name
                session_name = new_session_name
                if session_name not in manager.session_locks:
                    manager.session_locks[session_name] = asyncio.Lock()
                success = await manager.db_service.create_session(db, session_data)
                if not success:
                    raise Exception("Failed to create session in database after retry")

        manager.active_sessions[session_name] = session_data
        if session_data.websocket_session_id:
            manager.websocket_to_session[session_data.websocket_session_id] = session_name
        logger.info(
            "Created session %s (DB ID: %s, WebSocket: %s)",
            session_name,
            session_data.db_id,
            session_data.websocket_session_id,
        )
        return session_data


async def get_session_by_name(manager, session_name: str, owner_user_id: Optional[str] = None):
    if session_name in manager.active_sessions:
        session = manager.active_sessions[session_name]
        if owner_user_id and session.owner_user_id and session.owner_user_id != owner_user_id:
            return None
        return apply_progress(manager, session)

    async with AsyncSessionLocal() as db:
        session_data = await manager.db_service.get_session_by_name(db, session_name, owner_user_id=owner_user_id)
        if session_data:
            manager.active_sessions[session_name] = session_data
            if session_data.websocket_session_id:
                manager.websocket_to_session[session_data.websocket_session_id] = session_name
            return apply_progress(manager, session_data)
        return None


async def get_session_by_websocket_id(manager, websocket_session_id: str, owner_user_id: Optional[str] = None):
    if websocket_session_id in manager.websocket_to_session:
        session_name = manager.websocket_to_session[websocket_session_id]
        return await get_session_by_name(manager, session_name, owner_user_id=owner_user_id)

    async with AsyncSessionLocal() as db:
        session_data = await manager.db_service.get_session_by_websocket_id(
            db,
            websocket_session_id,
            owner_user_id=owner_user_id,
        )
        if session_data:
            manager.active_sessions[session_data.session_name] = session_data
            manager.websocket_to_session[websocket_session_id] = session_data.session_name
            return apply_progress(manager, session_data)
        return None


async def session_exists_by_name(manager, session_name: str) -> bool:
    return await get_session_by_name(manager, session_name) is not None


async def session_exists(manager, db_id: str, owner_user_id: Optional[str] = None) -> bool:
    try:
        async with AsyncSessionLocal() as db:
            return await manager.db_service.get_session(db, db_id, owner_user_id=owner_user_id) is not None
    except Exception as exc:
        logger.error("Error checking if session exists for %s: %s", db_id, exc)
        return False


async def get_session_by_db_id(manager, db_id: str, owner_user_id: Optional[str] = None):
    try:
        async with AsyncSessionLocal() as db:
            session = await manager.db_service.get_session(db, db_id, owner_user_id=owner_user_id)
            if session:
                return apply_progress(manager, manager.db_service.to_session_data(session))
            return None
    except Exception as exc:
        logger.error("Error getting session by db_id %s: %s", db_id, exc)
        return None


async def update_session_notes(manager, db_id: str, notes: str) -> bool:
    try:
        async with AsyncSessionLocal() as db:
            success = await manager.db_service.update_session_notes(db, db_id, notes)
            for session_data in manager.active_sessions.values():
                if session_data.db_id == db_id:
                    session_data.advisor_notes = notes
                    break
            return success
    except Exception as exc:
        logger.error("Error updating notes for db_id %s: %s", db_id, exc)
        return False


async def rename_session(manager, session_identifier: str, new_name: str):
    sanitized_name = new_name.strip()
    if not sanitized_name:
        raise ValueError("Session name cannot be empty")

    session = await get_session_by_name(manager, session_identifier)
    if not session:
        session = await get_session_by_db_id(manager, session_identifier)
    if not session:
        return None

    status_value = session.status.value if isinstance(session.status, SessionStatus) else str(session.status).lower()
    if status_value != SessionStatus.COMPLETED.value:
        raise ValueError("Sessions can only be renamed after completion")

    old_name = session.session_name
    if sanitized_name == old_name:
        return session

    async with AsyncSessionLocal() as db:
        try:
            await manager.db_service.rename_session(db, session.db_id, sanitized_name)
        except IntegrityError:
            raise ValueError("Session name already exists")

    session.session_name = sanitized_name
    session.updated_at = datetime.now()
    if old_name in manager.active_sessions:
        cached_session = manager.active_sessions.pop(old_name)
        cached_session.session_name = sanitized_name
        cached_session.updated_at = session.updated_at
        manager.active_sessions[sanitized_name] = cached_session

    for websocket_id, mapped_name in list(manager.websocket_to_session.items()):
        if mapped_name == old_name:
            manager.websocket_to_session[websocket_id] = sanitized_name

    if old_name in manager.session_locks:
        manager.session_locks[sanitized_name] = manager.session_locks.pop(old_name)
    if old_name in manager.processing_progress:
        manager.processing_progress[sanitized_name] = manager.processing_progress.pop(old_name)

    updated_session = await get_session_by_db_id(manager, session.db_id)
    return updated_session or session


async def set_session_status(manager, session_name: str, status: SessionStatus) -> bool:
    try:
        session = await get_session_by_name(manager, session_name)
        if not session:
            logger.warning("Attempted to update status for unknown session %s", session_name)
            return False

        async with AsyncSessionLocal() as db:
            success = await manager.db_service.update_session_status(db, session.db_id, status)

        if success:
            session.status = status
            session.updated_at = datetime.now()
            if status == SessionStatus.PROCESSING:
                manager.processing_progress[session_name] = {
                    "percent": 0.0,
                    "stage": "queued",
                    "message": "Queued for processing",
                    "updated_at": datetime.now(),
                }
            elif status == SessionStatus.COMPLETED:
                manager.processing_progress[session_name] = {
                    "percent": 100.0,
                    "stage": "completed",
                    "message": "Processing complete",
                    "updated_at": datetime.now(),
                }
            elif status == SessionStatus.ERROR:
                progress = manager.processing_progress.get(session_name, {})
                progress.update({
                    "stage": "error",
                    "message": progress.get("message") or "Processing failed",
                    "updated_at": datetime.now(),
                })
                manager.processing_progress[session_name] = progress
            elif status in (SessionStatus.ACTIVE, SessionStatus.PAUSED, SessionStatus.DISCONNECTED):
                manager.processing_progress.pop(session_name, None)
            logger.info("Session %s status updated to %s", session_name, status.value)
        return success
    except Exception as exc:
        logger.error("Failed to update status for session %s: %s", session_name, exc)
        return False


async def end_session(manager, session_name: str) -> bool:
    return await set_session_status(manager, session_name, SessionStatus.COMPLETED)


async def pause_session(manager, session_name: str) -> bool:
    return await set_session_status(manager, session_name, SessionStatus.PAUSED)


async def resume_session(manager, session_name: str) -> bool:
    return await set_session_status(manager, session_name, SessionStatus.ACTIVE)


async def get_session_stats(manager, session_name: str, owner_user_id: Optional[str] = None):
    try:
        session = await get_session_by_name(manager, session_name, owner_user_id=owner_user_id)
        if not session:
            return None
        async with AsyncSessionLocal() as db:
            return await manager.db_service.get_session_stats(db, session.db_id)
    except Exception as exc:
        logger.error("Error getting stats for %s: %s", session_name, exc)
        return None


async def list_active_sessions(manager, owner_user_id: Optional[str] = None):
    try:
        async with AsyncSessionLocal() as db:
            sessions = await manager.db_service.get_active_sessions(db, owner_user_id=owner_user_id)
            return [apply_progress(manager, session) for session in sessions]
    except Exception as exc:
        logger.error("Error listing active sessions: %s", exc)
        return []


async def get_all_sessions(manager, owner_user_id: Optional[str] = None):
    try:
        async with AsyncSessionLocal() as db:
            sessions = await manager.db_service.get_all_sessions(db, owner_user_id=owner_user_id)
            return [apply_progress(manager, session) for session in sessions]
    except Exception as exc:
        logger.error("Error getting all sessions: %s", exc)
        return []


async def cleanup_expired_sessions(manager, max_age_hours: int = 24, owner_user_id: Optional[str] = None) -> int:
    try:
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        async with AsyncSessionLocal() as db:
            return await manager.db_service.cleanup_expired_sessions(
                db,
                cutoff_time,
                owner_user_id=owner_user_id,
            )
    except Exception as exc:
        logger.error("Error cleaning up expired sessions: %s", exc)
        return 0


async def shutdown(manager):
    logger.info("SessionManager: Starting shutdown...")
    manager.active_sessions.clear()
    manager.websocket_to_session.clear()
    manager.processing_progress.clear()
    manager.session_locks.clear()
    logger.info("SessionManager: Shutdown complete")
