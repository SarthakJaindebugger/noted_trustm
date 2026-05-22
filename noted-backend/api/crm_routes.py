from fastapi import APIRouter, Depends, HTTPException

from api.auth import AuthenticatedUser, require_authenticated_user
from api.schemas import CRMFormUpdate
from database.connection import AsyncSessionLocal


crm_router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@crm_router.post("/sessions/{session_identifier}/crm-form")
async def generate_crm_form(
    session_identifier: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Auto-generate a CRM form from the session summary."""
    from database import models as db_models
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        session = await _resolve_session(db, session_identifier, current_user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await db.execute(
            select(db_models.CRMForm).where(db_models.CRMForm.session_id == session.session_id)
        )
        existing = result.scalars().first()
        if existing:
            return _crm_form_to_dict(existing)

        summary_result = await db.execute(
            select(db_models.SessionSummary).where(db_models.SessionSummary.session_id == session.session_id)
        )
        summary = summary_result.scalars().first()

        form = db_models.CRMForm(
            session_id=session.session_id,
            encounter_type="in-person",
            advisor_name=session.advisor_name,
            client_name=session.client_name,
            topics_discussed=summary.topics_discussed if summary else None,
            action_items=summary.action_items if summary else None,
            notes=session.advisor_notes,
            status="draft",
        )
        db.add(form)
        await db.commit()
        await db.refresh(form)
        return _crm_form_to_dict(form)


@crm_router.get("/sessions/{session_identifier}/crm-form")
async def get_crm_form(
    session_identifier: str,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Get the CRM form for a session."""
    from database import models as db_models
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        session = await _resolve_session(db, session_identifier, current_user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await db.execute(
            select(db_models.CRMForm).where(db_models.CRMForm.session_id == session.session_id)
        )
        form = result.scalars().first()
        if not form:
            raise HTTPException(status_code=404, detail="CRM form not found. Generate one first.")
        return _crm_form_to_dict(form)


@crm_router.put("/sessions/{session_identifier}/crm-form")
async def update_crm_form(
    session_identifier: str,
    data: CRMFormUpdate,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Update the CRM form for a session."""
    from database import models as db_models
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        session = await _resolve_session(db, session_identifier, current_user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await db.execute(
            select(db_models.CRMForm).where(db_models.CRMForm.session_id == session.session_id)
        )
        form = result.scalars().first()
        if not form:
            raise HTTPException(status_code=404, detail="CRM form not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(form, key, value)

        await db.commit()
        await db.refresh(form)
        return _crm_form_to_dict(form)


async def _resolve_session(db, identifier: str, owner_user_id: str):
    """Resolve a session by ID or name."""
    from database import models as db_models
    from sqlalchemy import select

    result = await db.execute(
        select(db_models.Session).where(
            (db_models.Session.session_id == identifier)
            | (db_models.Session.session_name == identifier)
        ).where(db_models.Session.owner_user_id == owner_user_id)
    )
    return result.scalars().first()


def _crm_form_to_dict(form) -> dict:
    return {
        "id": form.id,
        "session_id": form.session_id,
        "encounter_date": form.encounter_date.isoformat() if form.encounter_date else None,
        "encounter_type": form.encounter_type,
        "advisor_name": form.advisor_name,
        "client_name": form.client_name,
        "client_id": form.client_id,
        "topics_discussed": form.topics_discussed,
        "action_items": form.action_items,
        "follow_up_date": form.follow_up_date.isoformat() if form.follow_up_date else None,
        "follow_up_notes": form.follow_up_notes,
        "outcome": form.outcome,
        "referrals": form.referrals,
        "notes": form.notes,
        "status": form.status,
        "language": form.language,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "updated_at": form.updated_at.isoformat() if form.updated_at else None,
    }
