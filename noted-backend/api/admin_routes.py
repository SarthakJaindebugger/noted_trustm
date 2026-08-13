import logging
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import AuthenticatedUser, require_authenticated_user
from knowledgebase.admin_dashboard_stats import (
    DEFAULT_SUMMARY_OUTPUT,
    build_combined_summary,
)
from services.admin_audio_analysis import analyze_audio_file, list_user_audio_files, list_submitted_crm_forms, aggregate_all_crm_forms, clear_user_database

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Keep this identical to the generator's output path.  In Docker the app lives
# at /app, while in local development the repository root is one level above
# noted-backend; DEFAULT_SUMMARY_OUTPUT handles both layouts correctly.
COMBINED_DASHBOARD_SUMMARY = DEFAULT_SUMMARY_OUTPUT
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
    """Return the dashboard data published in the combined summary JSON file."""
    _ensure_admin(current_user)
    try:
        if not COMBINED_DASHBOARD_SUMMARY.is_file():
            raise HTTPException(
                status_code=404,
                detail="Dashboard summary file has not been generated yet",
            )

        with COMBINED_DASHBOARD_SUMMARY.open("r", encoding="utf-8") as summary_file:
            stats = json.load(summary_file)

        if not isinstance(stats, dict):
            raise ValueError("Dashboard summary must contain a JSON object")

        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to read dashboard summary")


@admin_router.post("/stats/refresh")
async def refresh_admin_stats(
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Regenerate the dashboard summary from all users' processed CRM JSON files."""
    _ensure_admin(current_user)
    try:
        stats = build_combined_summary(output_path=COMBINED_DASHBOARD_SUMMARY)
        return stats
    except Exception as e:
        logger.error("Failed to refresh dashboard summary: %s", e)
        raise HTTPException(status_code=500, detail="Failed to refresh dashboard summary")


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
        # Log the full error server-side but never expose raw exception text
        # (e.g. CUDA OOM traces) in the HTTP response.
        logger.error("Admin audio analysis failed for %s: %s", audio_path, exc)
        raise HTTPException(
            status_code=500,
            detail="Analysis failed. Please ensure the speech-analysis services are available and try again.",
        ) from exc

    return result


@admin_router.get("/crm-forms")
async def list_crm_forms(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """List all submitted CRM forms."""
    _ensure_admin(current_user)
    try:
        forms = list_submitted_crm_forms()
        return {"crm_forms": forms}
    except Exception as exc:
        logger.error("Failed to list CRM forms: %s", exc)
        return {"crm_forms": []}


@admin_router.post("/crm-forms/parse")
async def parse_crm_forms(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Parse and aggregate data from selected CRM forms only.
    
    Expected payload: { "file_paths": ["knowledgebase/submitted_crm_forms/foo.json", ...] }
    Returns the same shape as GET /crm-forms/aggregated so the frontend can apply it directly.
    """
    _ensure_admin(current_user)
    file_paths = payload.get("file_paths", [])
    if not file_paths:
        raise HTTPException(status_code=400, detail="file_paths is required")

    from services.admin_audio_analysis import aggregate_all_crm_forms, get_submitted_crm_root, REPO_ROOT
    import tempfile, shutil

    # Build a temporary directory containing only the selected files,
    # then run aggregate_all_crm_forms against it.
    try:
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            for fp_str in file_paths:
                src = Path(fp_str) if Path(fp_str).is_absolute() else REPO_ROOT / fp_str
                if src.exists() and src.is_file():
                    shutil.copy2(str(src), str(tmp_dir / src.name))
                else:
                    logger.warning("Selected CRM file not found: %s", src)

            result = aggregate_all_crm_forms(submitted_crm_root=tmp_dir)
        finally:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

        return result
    except Exception as exc:
        logger.error("Failed to parse selected CRM forms: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to parse CRM forms")


@admin_router.get("/crm-forms/aggregated")
async def get_aggregated_crm_data(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Get aggregated data from ALL submitted CRM forms for dashboard initialization."""
    _ensure_admin(current_user)
    try:
        aggregated = aggregate_all_crm_forms()
        return aggregated
    except Exception as exc:
        logger.error("Failed to aggregate CRM forms: %s", exc)
        return {
            "contact_methods": [],
            "topics_discussed": [],
            "labour_positions": [],
            "birth_countries": [],
            "languages": [],
            "residences": [],
            "purposes_of_visit": [],
            "encounter_types": [],
            "follow_up_notes": [],
            "total_forms": 0,
            "advisors": [],
            "clients": [],
        }


@admin_router.delete("/clear-user-database")
async def clear_database(current_user: AuthenticatedUser = Depends(require_authenticated_user)):
    """Delete all files from every user's subfolders and submitted CRM forms. Keeps folder structure."""
    _ensure_admin(current_user)
    try:
        result = clear_user_database()
        return result
    except Exception as exc:
        logger.error("Failed to clear user database: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to clear user database")
