import logging
import os
import uuid
from pathlib import Path
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
from services.account_store import principal_data_dir, recordings_dir_for_principal, uploads_dir_for_principal
from services.admin_audio_analysis import (
    analyze_audio_file,
    ensure_audio_belongs_to_user,
    list_audio_files_for_username,
    list_audio_files_categorized_for_username,
    save_submitted_crm_form,
)
from services.file_service import save_upload_file
from services.session_manager_async import AsyncSessionManager


logger = logging.getLogger(__name__)

session_router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@session_router.post("/audio/upload")
async def upload_user_audio(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Save an audio upload directly in the authenticated user's data folder."""
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    allowed_extensions = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
    if extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Please upload a supported audio file.")

    # User dashboard uploads now save under recordings/ per desired architecture.
    destination_dir = recordings_dir_for_principal("user", current_user.username)
    os.makedirs(destination_dir, exist_ok=True)

    try:
        filepath = await save_upload_file(file, destination_dir)
        logger.info("Saved audio upload for user %s to %s", current_user.username, filepath)
        return {"message": "Audio uploaded successfully.", "filename": Path(filepath).name}
    except Exception as exc:
        logger.error("Error saving audio upload for user %s: %s", current_user.username, exc)
        raise HTTPException(status_code=500, detail="Could not save the audio file.")


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


@session_router.get("/audio/analyze-files")
async def list_audio_files_for_analysis(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Return the audio files that belong to the authenticated user."""
    return {"audio_files": list_audio_files_for_username(current_user.username)}


@session_router.get("/audio/analyze-files-categorized")
async def list_audio_files_categorized(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Return audio files split into 'completed' and 'new' based on CRM form presence."""
    return list_audio_files_categorized_for_username(current_user.username)


@session_router.post("/audio/analyze")
async def analyze_selected_audio(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Run the speech-analysis pipeline on one of the user's own audio files."""
    audio_path = payload.get("audio_path")
    if not audio_path:
        raise HTTPException(status_code=400, detail="audio_path is required")

    try:
        ensure_audio_belongs_to_user(audio_path, current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = analyze_audio_file(audio_path)
    except Exception as exc:
        # Log the full backend error for debugging, but never leak it to the
        # frontend (e.g. CUDA out-of-memory dumps should not appear in the UI).
        logger.error("Audio analysis failed for user %s: %s", current_user.username, exc)
        raise HTTPException(
            status_code=500,
            detail="Analysis failed. Please ensure the speech-analysis services are available and try again.",
        ) from exc

    return result


@session_router.get("/audio/crm-form-submitted-data")
async def get_submitted_crm_form_data(
    audio_filename: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Return the submitted CRM form data for a given audio file."""
    from services.admin_audio_analysis import get_submitted_crm_root
    from speech_analysis_qa.utils import sanitize_username
    import json as _json

    safe_username = sanitize_username(current_user.username)
    root = get_submitted_crm_root()

    if not root.exists():
        raise HTTPException(status_code=404, detail="No submitted forms found.")

    audio_stem = Path(audio_filename).stem

    for file_path in sorted(root.glob(f"{safe_username}_*.json"), reverse=True):
        if not file_path.is_file():
            continue
        try:
            record = _json.loads(file_path.read_text(encoding="utf-8"))
            form_section = record.get("form", {})
            saved_audio = form_section.get("audio_filename", "")
            if saved_audio and Path(saved_audio).stem == audio_stem:
                return {"form": form_section}
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="No submitted form found for this audio file.")


@session_router.get("/audio/crm-form-status")
async def get_crm_form_status(
    audio_filename: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Check if a submitted CRM form exists for the given audio file (saved via Save button)."""
    from services.admin_audio_analysis import get_submitted_crm_root
    from speech_analysis_qa.utils import sanitize_username
    import json as _json

    safe_username = sanitize_username(current_user.username)
    root = get_submitted_crm_root()

    if not root.exists():
        return {"crm_form_exists": False}

    audio_stem = Path(audio_filename).stem

    for file_path in root.glob(f"{safe_username}_*.json"):
        if not file_path.is_file():
            continue
        try:
            record = _json.loads(file_path.read_text(encoding="utf-8"))
            form_section = record.get("form", {})
            saved_audio = form_section.get("audio_filename", "")
            if saved_audio and Path(saved_audio).stem == audio_stem:
                return {"crm_form_exists": True}
        except Exception:
            continue

    return {"crm_form_exists": False}


@session_router.get("/audio/crm-form-submissions")
async def get_all_crm_form_submissions(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Return a set of audio filenames for which the user has submitted CRM forms."""
    from services.admin_audio_analysis import get_submitted_crm_root
    from speech_analysis_qa.utils import sanitize_username
    import json as _json

    safe_username = sanitize_username(current_user.username)
    root = get_submitted_crm_root()
    submitted = []

    if root.exists():
        for file_path in root.glob(f"{safe_username}_*.json"):
            if not file_path.is_file():
                continue
            try:
                record = _json.loads(file_path.read_text(encoding="utf-8"))
                form_section = record.get("form", {})
                audio_fn = form_section.get("audio_filename", "")
                if audio_fn:
                    submitted.append(audio_fn)
            except Exception:
                continue

    return {"submitted_audio_files": submitted}


@session_router.get("/audio/analyze-result")
async def get_existing_analysis_result(
    audio_path: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Return the analysis output paths for an already-analyzed audio file without re-running the pipeline.

    Used by the frontend after a page refresh to re-enable the CRM form button for files
    that were previously analyzed.
    """
    import re as _re
    from services.admin_audio_analysis import (
        ensure_audio_belongs_to_user,
        get_default_users_root,
        REPO_ROOT,
    )
    from speech_analysis_qa.utils import sanitize_username

    try:
        ensure_audio_belongs_to_user(audio_path, current_user.username)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    users_root = get_default_users_root()
    safe_username = sanitize_username(current_user.username)
    user_uploads = users_root / safe_username / "uploads"

    if not user_uploads.exists():
        raise HTTPException(status_code=404, detail="No analysis results found.")

    audio_stem = _re.sub(r"[^A-Za-z0-9._-]+", "_", Path(audio_path).stem).strip("._-")
    matching = sorted(
        [d for d in user_uploads.iterdir() if d.is_dir() and d.name.startswith(audio_stem)],
        reverse=True,
    )

    if not matching:
        raise HTTPException(status_code=404, detail="No analysis results found for this file.")

    target_dir = matching[0]

    crm_form_json_path = None
    crm_form_html_path = None
    for candidate in (target_dir / "crm_form_parsed.json", target_dir / "6_crm_form_parsed.json"):
        if candidate.exists():
            crm_form_json_path = str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            break
    for candidate in (target_dir / "crm_form_parsed.html", target_dir / "6_crm_form.html"):
        if candidate.exists():
            crm_form_html_path = str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            break

    if not crm_form_html_path:
        raise HTTPException(status_code=404, detail="CRM form HTML not found for this file.")

    return {
        "output_dir": str(target_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
        "crm_form_json_path": crm_form_json_path,
        "crm_form_html_path": crm_form_html_path,
        "result": None,
    }


@session_router.post("/audio/crm-form/submit")
async def submit_crm_form_copy(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Submit a CRM form by copying the existing 6_crm_form_parsed.json from the user's
    uploads folder into knowledgebase/submitted_crm_forms.

    The payload must contain 'audio_filename' (e.g. 'dia03sce1SA.wav' or stem only).
    """
    import re as _re
    import shutil as _shutil
    from datetime import datetime as _datetime
    from services.admin_audio_analysis import (
        get_default_users_root,
        get_submitted_crm_root,
        REPO_ROOT,
    )
    from speech_analysis_qa.utils import sanitize_username

    audio_filename = payload.get("audio_filename") or payload.get("audio_path", "")
    audio_stem = Path(audio_filename).stem  # strip extension if present
    audio_stem_safe = _re.sub(r"[^A-Za-z0-9._-]+", "_", audio_stem).strip("._-")

    users_root = get_default_users_root()
    safe_username = sanitize_username(current_user.username)
    user_uploads = users_root / safe_username / "uploads"

    logger.info(
        "[CRM_SUBMIT] user=%s audio_stem=%s user_uploads=%s",
        safe_username, audio_stem_safe, user_uploads,
    )

    if not user_uploads.exists():
        raise HTTPException(status_code=404, detail=f"No uploads folder for user {safe_username}")

    # Find the most recent upload dir matching this audio stem
    matching_dirs = sorted(
        [d for d in user_uploads.iterdir() if d.is_dir() and d.name.startswith(audio_stem_safe)],
        reverse=True,
    )
    logger.info("[CRM_SUBMIT] matching dirs: %s", [d.name for d in matching_dirs])

    source_json = None
    for d in matching_dirs:
        for candidate_name in ("6_crm_form_parsed.json", "crm_form_parsed.json"):
            candidate = d / candidate_name
            if candidate.exists():
                source_json = candidate
                break
        if source_json:
            break

    if not source_json:
        logger.error("[CRM_SUBMIT] No CRM JSON found for %s in %s", audio_stem_safe, user_uploads)
        raise HTTPException(
            status_code=404,
            detail=f"No CRM form JSON found for '{audio_stem}'. Please run analysis first.",
        )

    logger.info("[CRM_SUBMIT] Found source JSON: %s", source_json)

    # Destination: knowledgebase/submitted_crm_forms/<username>_<DD.MM.YYYY>_<HH_MM_SS>.json
    dest_root = get_submitted_crm_root()
    dest_root.mkdir(parents=True, exist_ok=True)
    stamp = _datetime.now().strftime("%d.%m.%Y_%H_%M_%S")
    dest_filename = f"{safe_username}_{stamp}.json"
    dest_path = dest_root / dest_filename

    logger.info("[CRM_SUBMIT] Copying %s → %s", source_json, dest_path)
    _shutil.copy2(str(source_json), str(dest_path))

    if not dest_path.exists():
        logger.error("[CRM_SUBMIT] Copy failed — dest file does not exist after copy")
        raise HTTPException(status_code=500, detail="File copy failed.")

    logger.info("[CRM_SUBMIT] SUCCESS — saved %s (%d bytes)", dest_path.name, dest_path.stat().st_size)
    return {
        "success": True,
        "filename": dest_filename,
        "source": str(source_json.relative_to(REPO_ROOT)).replace("\\", "/"),
        "dest": str(dest_path.relative_to(REPO_ROOT)).replace("\\", "/"),
    }


@session_router.post("/audio/crm-form/save")
async def save_crm_form_from_html(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Save a submitted CRM form from the HTML popup directly to knowledgebase/submitted_crm_forms.

    This endpoint is called by the CRM HTML form's submit button.
    The payload contains the full form data including all questionnaire fields.
    """
    try:
        result = save_submitted_crm_form(
            username=current_user.username,
            form_data=payload,
        )
        logger.info(
            "CRM form saved for user %s: %s",
            current_user.username,
            result.get("filename"),
        )
        return {"success": True, "filename": result["filename"], "path": result["path"]}
    except Exception as exc:
        logger.error(
            "Failed to save CRM form for user %s: %s",
            current_user.username,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to save CRM form.")


@session_router.get("/audio/file-content")
async def read_user_audio_file_content(
    path: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Read a text file (e.g. CRM form HTML) within the user's own directory."""
    from pathlib import Path as _Path
    from speech_analysis_qa.utils import sanitize_username

    repo_root = _Path(__file__).resolve().parents[2]

    requested = _Path(path)

    if not requested.is_absolute():
        requested = repo_root / requested

    resolved = requested.resolve()

    # Ensure the file belongs to the authenticated user's directory
    safe_username = sanitize_username(current_user.username)

    valid_prefix = (
        repo_root
        / "knowledgebase"
        / "users_admin_data"
        / "users"
        / safe_username
    )

    if not str(resolved).startswith(str(valid_prefix.resolve())):
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    supported_text = {
        "html",
        "htm",
        "json",
        "md",
        "txt",
        "css",
        "js",
        "csv",
    }

    extension = resolved.suffix.lower().lstrip(".")

    if extension not in supported_text:
        raise HTTPException(
            status_code=415,
            detail=f"Preview not supported for .{extension} files"
        )

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    try:
        # For CRM HTML files, always regenerate from the current template
        if resolved.name == "crm_form_parsed.html":
            json_sibling = resolved.with_name("crm_form_parsed.json")
            template_path = repo_root / "crm_forms" / "crm_form_template.html"
            if json_sibling.exists() and template_path.exists():
                import json as _json
                parsed_data = _json.loads(json_sibling.read_text(encoding="utf-8"))
                template_html = template_path.read_text(encoding="utf-8")
                form_payload = parsed_data.get("form", {})
                questionnaire = parsed_data.get("questionnaire", {})
                metadata = parsed_data.get("metadata", {})
                initial_data = {"form": form_payload, "questionnaire": questionnaire, "metadata": metadata}
                json_text = _json.dumps(initial_data, ensure_ascii=False).replace("</", "<\\/")
                injection = f"<script>window.initialData = {json_text};</script>"
                content = template_html.replace("<!-- INITIAL_FORM_DATA_PLACEHOLDER -->", injection)
            else:
                content = resolved.read_text(encoding="utf-8", errors="replace")
        else:
            content = resolved.read_text(encoding="utf-8", errors="replace")

    except Exception as exc:
        logger.error(
            "Failed to read file %s: %s",
            resolved,
            exc
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to read file"
        )

    return {
        "path": str(
            resolved.relative_to(repo_root)
        ).replace("\\", "/"),
        "name": resolved.name,
        "content": content,
        "extension": extension,
    }

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
        uploads_dir = uploads_dir_for_principal(
            current_user.id,
            username=current_user.username,
            role=current_user.role,
        )
        os.makedirs(uploads_dir, exist_ok=True)
        filepath = await save_upload_file(file, uploads_dir)

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
