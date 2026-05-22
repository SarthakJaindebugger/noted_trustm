import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.auth import AuthenticatedUser, require_authenticated_user
from api.route_support import (
    extract_session_topics,
    get_audio_processor,
    get_or_generate_summary_record,
    get_session_manager,
    get_transcript_entries_for_session,
    resolve_session_or_404,
    summary_record_to_response,
    transcript_entries_to_segments,
    transcript_entries_to_text,
)
from api.schemas import (
    ExperimentOutputRequest,
    SessionOverviewUpdateRequest,
    SessionSummaryUpdateRequest,
    SessionTranslateRequest,
)
from api.translation_support import build_summary_text, translate_text
from models.session import SessionSummary
from services.session_manager_async import AsyncSessionManager


logger = logging.getLogger(__name__)

summary_router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@summary_router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Get AI-generated session summary."""
    session = await resolve_session_or_404(session_manager, session_id, current_user)
    summary_record = await get_or_generate_summary_record(session_manager, session)
    if summary_record:
        return summary_record_to_response(session_id, summary_record)

    transcript = await get_transcript_entries_for_session(session_manager, session)
    if not transcript:
        return SessionSummary(
            session_id=session_id,
            overview="No conversation data available yet.",
            action_items=[],
            topics_discussed=[],
            related_services=[],
        )

    return SessionSummary(
        session_id=session_id,
        overview="Summary generation did not complete. Re-run summary generation for this session.",
        action_items=[],
        topics_discussed=[],
        related_services=[],
        output_for=[],
        confidence_score=0.0,
    )


@summary_router.get("/topic-summary/{session_id}")
async def generate_topic_summary(
    session_id: str,
    topic: str = "",
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Generate a topic-focused summary from the session transcript."""
    if not topic.strip():
        raise HTTPException(status_code=400, detail="Topic query parameter is required")

    session = await resolve_session_or_404(session_manager, session_id, current_user)
    transcript_entries = await get_transcript_entries_for_session(session_manager, session)
    if not transcript_entries:
        raise HTTPException(status_code=404, detail="No transcript available for this session")

    segments = transcript_entries_to_segments(transcript_entries)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript is empty")

    from audio.chunker import Summarizer

    try:
        summarizer = Summarizer()
        return await summarizer.summarize_topic(topic.strip(), segments)
    except Exception as exc:
        logger.error(
            "Failed to generate topic summary for session %s, topic '%s': %s",
            session_id,
            topic,
            exc,
        )
        raise HTTPException(status_code=500, detail=f"Failed to generate topic summary: {exc}")


@summary_router.get("/summary/{session_id}")
async def summary(
    session_id: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    await resolve_session_or_404(session_manager, session_id, current_user)
    audio_processor, _ = get_audio_processor()
    summary_payload = audio_processor.get_auto_summary(session_id)
    if summary_payload is None:
        raise HTTPException(status_code=404, detail="No live summary available for this session")
    return {"summary": summary_payload}


@summary_router.put("/sessions/{session_identifier}/overview")
async def update_session_overview(
    session_identifier: str,
    request: SessionOverviewUpdateRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Update the executive summary / overview for a session."""
    try:
        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        await session_manager.save_session_summary(session.session_name, {"overview": request.overview})
        return {"message": "Overview updated successfully", "overview": request.overview}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating overview for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@summary_router.put("/sessions/{session_identifier}/summary")
async def update_session_summary(
    session_identifier: str,
    request: SessionSummaryUpdateRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Update stored summary fields for a session."""
    try:
        summary_updates = request.model_dump(exclude_unset=True)
        if not summary_updates:
            raise HTTPException(status_code=400, detail="No summary fields provided")

        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        await session_manager.save_session_summary(session.session_name, summary_updates)
        return {"message": "Summary updated successfully", **summary_updates}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating summary for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@summary_router.post("/sessions/{session_identifier}/translate-summary")
async def translate_session_summary(
    session_identifier: str,
    request: SessionTranslateRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Translate the stored session summary into the requested language."""
    try:
        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        stored_summary = await get_or_generate_summary_record(session_manager, session)
        if not stored_summary:
            raise HTTPException(
                status_code=404,
                detail="No summary found for this session. Complete the session first.",
            )

        summary_text = build_summary_text(stored_summary)
        if not summary_text.strip():
            raise HTTPException(status_code=404, detail="Summary is empty")

        audio_processor, _ = get_audio_processor()
        loop = asyncio.get_running_loop()
        translated_summary = await loop.run_in_executor(
            None,
            lambda: translate_text(audio_processor, summary_text, request.language, stored_summary),
        )

        return {
            "session_id": session_identifier,
            "target_language": request.language,
            "translated_summary": translated_summary,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error translating summary for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@summary_router.post("/sessions/{session_identifier}/experiment-output")
async def generate_experiment_output(
    session_identifier: str,
    request: ExperimentOutputRequest,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Generate custom experiment output (UI + content selection) for a session."""
    try:
        ui_map = {
            "full text": "full_text",
            "full_text": "full_text",
            "text": "full_text",
            "list": "list",
            "diagram": "diagram",
        }
        content_map = {
            "action points": "action_points",
            "action_points": "action_points",
            "service names": "service_names",
            "service_names": "service_names",
            "q&a": "qa",
            "qa": "qa",
            "q and a": "qa",
            "recap": "recap",
        }

        normalized_ui = ui_map.get(request.ui_type.lower(), request.ui_type.lower().replace(" ", "_"))
        normalized_content = content_map.get(
            request.content_type.lower(),
            request.content_type.lower().replace(" ", "_"),
        )

        allowed_ui = {"full_text", "list", "diagram"}
        allowed_content = {"action_points", "service_names", "qa", "recap"}

        if normalized_ui not in allowed_ui:
            raise HTTPException(status_code=400, detail=f"Unsupported ui_type: {request.ui_type}")
        if normalized_content not in allowed_content:
            raise HTTPException(status_code=400, detail=f"Unsupported content_type: {request.content_type}")

        session = await resolve_session_or_404(session_manager, session_identifier, current_user)
        transcript_entries = await get_transcript_entries_for_session(session_manager, session)
        transcript_text = transcript_entries_to_text(transcript_entries)
        if not transcript_text.strip():
            raise HTTPException(status_code=404, detail="Transcript not available for this session yet")

        audio_processor, _ = get_audio_processor()
        summary_record = await get_or_generate_summary_record(session_manager, session)
        session_topics = extract_session_topics(summary_record)

        return audio_processor.generate_experiment_output(
            transcript_text,
            normalized_ui,
            normalized_content,
            session_topics=session_topics,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error generating experiment output for session %s: %s", session_identifier, exc)
        raise HTTPException(status_code=500, detail=str(exc))
