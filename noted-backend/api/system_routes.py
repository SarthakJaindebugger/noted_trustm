import logging

from fastapi import APIRouter, Depends

from api.auth import AuthenticatedUser, authenticate_credentials, issue_access_token, require_authenticated_user
from api.route_support import get_session_manager
from api.schemas import LoginRequest
from config import settings
from services.model_manager import model_manager
from services.session_manager_async import AsyncSessionManager


logger = logging.getLogger(__name__)

system_router = APIRouter()


@system_router.post("/auth/login")
async def login(payload: LoginRequest):
    """Issue a signed bearer token for a configured user or administrator account."""
    user = authenticate_credentials(payload.username, payload.password)
    return {
        "access_token": issue_access_token(user),
        "token_type": "bearer",
        "expires_in": settings.auth.token_ttl_seconds,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
        },
    }


@system_router.post("/cleanup", dependencies=[Depends(require_authenticated_user)])
async def cleanup_expired_sessions(
    max_age_hours: int = 24,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    cleaned = await session_manager.cleanup_expired_sessions(
        max_age_hours,
        owner_user_id=current_user.id,
    )
    return {"message": f"Cleaned up {cleaned} expired sessions"}


@system_router.get("/status", dependencies=[Depends(require_authenticated_user)])
async def get_service_status():
    return {
        "status": "healthy",
        "services": {
            **model_manager.get_model_status(),
            "session_manager": "ready",
            "database": "ready",
        },
        "models": {
            "asr_batch_model": settings.models.asr_batch.name,
            "asr_batch_url": settings.models.asr_batch.url,
            "diarization_model": settings.models.diarization.name,
            "diarization_url": settings.models.diarization.url,
            "generation_model": settings.models.generation.name,
            "generation_url": settings.models.generation.url,
            "embedding_model": settings.models.embedding.name,
            "embedding_url": settings.models.embedding.url,
        },
        "version": "1.0.0",
    }
