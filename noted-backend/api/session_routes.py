import logging
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile

from api.auth import AuthenticatedUser, require_authenticated_user
from api.route_support import (
    get_session_manager,
    get_transcript_entries_for_session,
    resolve_session_or_404,
)
from api.schemas import SessionNotesUpdateRequest, SessionRenameRequest
from database.connection import AsyncSessionLocal
from models.session import SessionData, SessionStats, SessionStatus
from models.transcript import TranscriptEntry
from services.file_service import save_upload_file
from services.session_manager_async import AsyncSessionManager


logger = logging.getLogger(__name__)

session_router = APIRouter(dependencies=[Depends(require_authenticated_user)])


async def process_uploaded_audio(
    session_name: str,
    filepath: str,
    session_manager: AsyncSessionManager,
):
    """Background task to process an uploaded audio file."""
    try:
        from api.websocket import manager

        logger.info("Starting background processing for uploaded file %s on session %s", filepath, session_name)
        await session_manager.set_session_progress(session_name, 2.0, "loading", "Loading uploaded audio")
        success = await manager._process_full_session_audio(session_name, filepath)
        if success:
            await session_manager.set_session_progress(session_name, 100.0, "completed", "Processing complete")
            await session_manager.set_session_status(session_name, SessionStatus.COMPLETED)
            logger.info("Finished background processing for session %s", session_name)
        else:
            await session_manager.set_session_progress(session_name, 100.0, "error", "Processing failed")
            await session_manager.set_session_status(session_name, SessionStatus.ERROR)
            logger.error("Background processing failed for session %s", session_name)
    except Exception as exc:
        logger.error("Error during background audio processing for session %s: %s", session_name, exc)
        await session_manager.set_session_progress(session_name, 100.0, "error", "Processing failed")
        await session_manager.set_session_status(session_name, SessionStatus.ERROR)


@session_router.get("/sessions/next-name")
async def get_next_session_name(
    session_manager: AsyncSessionManager = Depends(get_session_manager),
):
    try:
        return {"next_session_name": await session_manager.get_next_session_name()}
    except Exception as exc:
        logger.error("Error getting next session name: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@session_router.post("/sessions", response_model=SessionData)
async def create_session(
    response: Response,
    session_name: Optional[str] = None,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        db_id = str(uuid.uuid4())
        if not session_name:
            session_name = await session_manager.generate_session_name()

        websocket_session_id = str(uuid.uuid4())
        session_data = SessionData(
            db_id=db_id,
            session_name=session_name,
            websocket_session_id=websocket_session_id,
            status=SessionStatus.ACTIVE,
            owner_user_id=current_user.id,
            owner_username=current_user.username,
        )
        session = await session_manager.create_session(session_data)

        response.set_cookie(
            key="websocket_session_id",
            value=websocket_session_id,
            max_age=86400,
            httponly=False,
            secure=True,
            samesite="lax",
            domain=None,
            path="/",
        )
        return {**session.dict(), "websocket_session_id": websocket_session_id}
    except Exception as exc:
        logger.error("Error creating session: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@session_router.get("/sessions/{session_identifier}", response_model=SessionData)
async def get_session(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    return await resolve_session_or_404(session_manager, session_identifier, current_user)


@session_router.get("/sessions/{session_identifier}/progress")
async def get_session_progress(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)
    progress = await session_manager.get_session_progress(session.session_name)
    if not progress:
        raise HTTPException(status_code=404, detail="Session not found")
    return progress


@session_router.put("/sessions/{session_identifier}/pause")
async def pause_session(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)
    if not await session_manager.pause_session(session.session_name):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session paused", "session_name": session.session_name}


@session_router.put("/sessions/{session_identifier}/resume")
async def resume_session(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)
    if not await session_manager.resume_session(session.session_name):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session resumed", "session_name": session.session_name}


@session_router.put("/sessions/{session_identifier}/end")
async def end_session(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)

    from api.websocket import manager

    audio_filepath = await manager.save_session_audio(session.session_name)
    if not await session_manager.end_session(session.session_name):
        raise HTTPException(status_code=404, detail="Session not found")

    response = {"message": "Session ended", "session_name": session.session_name}
    if audio_filepath:
        response["audio_saved"] = audio_filepath
    return response


@session_router.post("/sessions/{session_identifier}/upload-audio")
async def upload_audio_file(
    session_identifier: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)

    try:
        recordings_dir = "recordings"
        os.makedirs(recordings_dir, exist_ok=True)
        filepath = await save_upload_file(file, recordings_dir)

        await session_manager.set_session_status(session.session_name, SessionStatus.PROCESSING)
        await session_manager.set_session_progress(session.session_name, 0.0, "queued", "Queued for processing")
        logger.info("Uploaded file saved to %s for session %s", filepath, session.session_name)

        background_tasks.add_task(process_uploaded_audio, session.session_name, filepath, session_manager)
        return {
            "message": "File uploaded successfully and is being processed.",
            "session_name": session.session_name,
            "filename": file.filename,
        }
    except Exception as exc:
        logger.error("Error uploading file for session %s: %s", session.session_name, exc)
        raise HTTPException(status_code=500, detail=f"Could not process file: {exc}")


@session_router.get("/sessions", response_model=List[SessionData])
async def list_sessions(
    active_only: bool = True,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    if active_only:
        return await session_manager.list_active_sessions(owner_user_id=current_user.id)
    return await session_manager.get_all_sessions(owner_user_id=current_user.id)


@session_router.put("/sessions/{session_identifier}/rename", response_model=SessionData)
async def rename_session(
    session_identifier: str,
    payload: SessionRenameRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        renamed_session = await session_manager.rename_session(session.db_id, payload.session_name)
        if not renamed_session:
            raise HTTPException(status_code=404, detail="Session not found")
        return renamed_session
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Error renaming session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail="Failed to rename session")


@session_router.get("/sessions/{session_identifier}/transcript", response_model=List[TranscriptEntry])
async def get_session_transcript(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)
    return await get_transcript_entries_for_session(session_manager, session)


@session_router.get("/sessions/{session_identifier}/stats", response_model=SessionStats)
async def get_session_stats(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    session = await resolve_session_or_404(session_manager, session_identifier, current_user)
    stats = await session_manager.get_session_stats(session.session_name, owner_user_id=current_user.id)
    if not stats:
        raise HTTPException(status_code=404, detail="Session not found")
    return stats


@session_router.delete("/sessions/bulk")
async def bulk_delete_sessions(
    request: Request,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        body = await request.json()
        session_ids = body if isinstance(body, list) else body.get("session_ids", [])
        if not session_ids:
            raise HTTPException(status_code=400, detail="No session IDs provided")

        deleted_count = 0
        failed_sessions = []
        async with AsyncSessionLocal() as db:
            for session_identifier in session_ids:
                try:
                    success = await session_manager.db_service.delete_session(
                        db,
                        session_identifier,
                        owner_user_id=current_user.id,
                    )
                    if success:
                        deleted_count += 1
                    else:
                        failed_sessions.append(session_identifier)
                except Exception as exc:
                    logger.error("Failed to delete session %s: %s", session_identifier, exc)
                    failed_sessions.append(session_identifier)

        return {
            "message": f"Deleted {deleted_count} sessions",
            "deleted_count": deleted_count,
            "failed_sessions": failed_sessions,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in bulk delete: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@session_router.delete("/sessions/{session_identifier}")
async def delete_session(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    async with AsyncSessionLocal() as db:
        success = await session_manager.db_service.delete_session(
            db,
            session_identifier,
            owner_user_id=current_user.id,
        )

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted", "session_id": session_identifier}


@session_router.get("/sessions/{session_identifier}/notes")
async def get_session_notes(
    session_identifier: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        return {"notes": getattr(session, "advisor_notes", "") or ""}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting notes for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@session_router.put("/sessions/{session_identifier}/notes")
async def update_session_notes(
    session_identifier: str,
    request: SessionNotesUpdateRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    try:
        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        success = await session_manager.update_session_notes(session.db_id, request.notes)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update notes")
        return {"message": "Notes updated successfully", "notes": request.notes}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating notes for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))
