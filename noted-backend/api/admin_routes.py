import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import AuthenticatedUser, require_authenticated_user
from knowledgebase.admin_dashboard_stats import fetch_all_stats
from services.admin_audio_analysis import analyze_audio_file, list_user_audio_files

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
admin_router = APIRouter(prefix="/admin")


def _ensure_admin(current_user: AuthenticatedUser) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def _normalize_path(path: Optional[str]) -> Path:
    if not path:
        return REPO_ROOT

    requested = Path(path)
    if requested.is_absolute():
        resolved = requested.resolve()
    else:
        resolved = (REPO_ROOT / requested).resolve()

    if not str(resolved).startswith(str(REPO_ROOT)):
        raise HTTPException(status_code=403, detail="Path traversal is not allowed")
    return resolved


@admin_router.get("/stats")
async def get_admin_stats(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Return aggregated admin dashboard stats by reading processed JSON outputs."""
    _ensure_admin(current_user)
    try:
        stats = fetch_all_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch admin stats")


@admin_router.get("/files")
async def list_admin_files(
    path: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    _ensure_admin(current_user)
    target = _normalize_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File or directory not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Requested path must be a directory")

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        entries.append({
            "name": child.name,
            "path": str(child.relative_to(REPO_ROOT)).replace("\\", "/"),
            "is_dir": child.is_dir(),
            "size": child.stat().st_size if child.is_file() else None,
            "modified": child.stat().st_mtime,
            "extension": child.suffix.lower().lstrip("."),
        })

    return {
        "path": str(target.relative_to(REPO_ROOT)).replace("\\", "/"),
        "entries": entries,
    }


@admin_router.get("/files/content")
async def read_admin_file(
    path: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    _ensure_admin(current_user)
    target = _normalize_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    supported_text = {
        "py",
        "json",
        "md",
        "txt",
        "yml",
        "yaml",
        "js",
        "ts",
        "html",
        "css",
        "vue",
        "jsonl",
        "csv",
    }
    extension = target.suffix.lower().lstrip(".")
    if extension not in supported_text:
        raise HTTPException(status_code=415, detail=f"Preview not supported for .{extension} files")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error("Failed to read file %s: %s", target, e)
        raise HTTPException(status_code=500, detail="Failed to read file")

    return {
        "path": str(target.relative_to(REPO_ROOT)).replace("\\", "/"),
        "name": target.name,
        "content": content,
        "extension": extension,
    }


@admin_router.get("/audio-files")
async def list_audio_files_for_analysis(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    _ensure_admin(current_user)
    return {"audio_files": list_user_audio_files()}


@admin_router.post("/analyze-audio")
async def analyze_selected_audio(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    _ensure_admin(current_user)
    audio_path = payload.get("audio_path")
    if not audio_path:
        raise HTTPException(status_code=400, detail="audio_path is required")

    try:
        result = analyze_audio_file(audio_path)
    except Exception as exc:
        logger.error("Admin audio analysis failed for %s: %s", audio_path, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result
