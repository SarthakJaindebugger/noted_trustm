from typing import Any, Dict, List, Optional

from pydantic import BaseModel, constr


class SessionRenameRequest(BaseModel):
    session_name: constr(strip_whitespace=True, min_length=1, max_length=255)


class SessionSummaryUpdateRequest(BaseModel):
    overview: Optional[str] = None
    action_items: Optional[List[str]] = None
    topics_discussed: Optional[List[Any]] = None
    related_services: Optional[List[Dict[str, Any]]] = None
    output_for: Optional[List[str]] = None
    confidence_score: Optional[float] = None


class SessionNotesUpdateRequest(BaseModel):
    notes: str = ""


class SessionOverviewUpdateRequest(BaseModel):
    overview: str = ""


class SessionTranslateRequest(BaseModel):
    language: constr(strip_whitespace=True, min_length=2, max_length=32)


class ExperimentOutputRequest(BaseModel):
    ui_type: constr(strip_whitespace=True, min_length=1, max_length=64)
    content_type: constr(strip_whitespace=True, min_length=1, max_length=64)


class LoginRequest(BaseModel):
    username: constr(strip_whitespace=True, min_length=1, max_length=128)
    password: constr(min_length=1, max_length=256)


class CRMFormCreate(BaseModel):
    encounter_type: Optional[str] = None
    advisor_name: Optional[str] = None
    client_name: Optional[str] = None
    client_id: Optional[str] = None
    topics_discussed: Optional[list] = None
    action_items: Optional[list] = None
    follow_up_date: Optional[str] = None
    follow_up_notes: Optional[str] = None
    outcome: Optional[str] = None
    referrals: Optional[list] = None
    notes: Optional[str] = None
    language: Optional[str] = None


class CRMFormUpdate(CRMFormCreate):
    status: Optional[str] = None
