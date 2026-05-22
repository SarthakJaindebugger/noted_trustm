import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SessionSummary


logger = logging.getLogger(__name__)


class SummaryStore:
    async def save_session_summary(
        self,
        db: AsyncSession,
        session_id: str,
        summary_data: Dict[str, Any],
    ) -> SessionSummary:
        try:
            existing = await db.execute(
                select(SessionSummary).where(SessionSummary.session_id == session_id)
            )
            summary = existing.scalar_one_or_none()

            if summary:
                for key, value in summary_data.items():
                    if hasattr(summary, key):
                        setattr(summary, key, value)
                from datetime import datetime

                summary.updated_at = datetime.now()
            else:
                summary = SessionSummary(session_id=session_id, **summary_data)
                db.add(summary)

            await db.commit()
            await db.refresh(summary)
            return summary
        except Exception as exc:
            logger.error("Error saving summary for session %s: %s", session_id, exc)
            await db.rollback()
            raise

    async def get_session_summary(self, db: AsyncSession, session_id: str) -> Optional[SessionSummary]:
        try:
            result = await db.execute(
                select(SessionSummary).where(SessionSummary.session_id == session_id)
            )
            return result.scalar_one_or_none()
        except Exception as exc:
            logger.error("Error getting summary for session %s: %s", session_id, exc)
            return None
