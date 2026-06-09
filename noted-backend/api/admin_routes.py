import logging

from fastapi import APIRouter, HTTPException

from knowledgebase.admin_dashboard_stats import fetch_all_stats

logger = logging.getLogger(__name__)

# Temporarily public for local testing; add auth requirement later
admin_router = APIRouter(prefix="/admin")


@admin_router.get("/stats")
async def get_admin_stats():
    """Return aggregated admin dashboard stats by reading processed JSON outputs.
    
    NOTE: Temporarily public for local testing. Add require_authenticated_user dependency later.
    """
    try:
        stats = fetch_all_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch admin stats")
