from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

class SessionStatus(str, Enum):
    ACTIVE = "active"
    PROCESSING = "processing"
    PAUSED = "paused" 
    COMPLETED = "completed"
    DISCONNECTED = "disconnected"
    ERROR = "error"

class SessionData(BaseModel):
    # Database UUID - permanent identifier for storage
    db_id: str                         # UUID for database records
    # Human-readable session name shown in frontend  
    session_name: str                  # e.g. "SES-00001"
    # Temporary WebSocket session ID for real-time communication
    websocket_session_id: Optional[str] = None  # UUID for WebSocket connections
    
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Session metadata
    owner_user_id: Optional[str] = None
    owner_username: Optional[str] = None
    client_name: Optional[str] = None
    advisor_name: Optional[str] = None
    service_type: Optional[str] = None
    advisor_notes: Optional[str] = None
    
    # Processing stats
    total_duration: float = 0.0
    speech_duration: float = 0.0
    processing_time: float = 0.0
    processing_progress: float = 0.0
    processing_stage: Optional[str] = None
    processing_message: Optional[str] = None
    
    class Config:
        # Optional: Allow assignment of session_name even if not in constructor
        populate_by_name = True

class SessionStats(BaseModel):
    session_id: str
    total_chunks_processed: int = 0
    total_audio_duration: float = 0.0
    total_speech_duration: float = 0.0
    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    speakers_identified: int = 0
    languages_detected: List[str] = []
    
class SessionSummary(BaseModel):
    session_id: str
    overview: str
    action_items: List[str] = Field(default_factory=list)
    topics_discussed: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    related_services: List[Dict[str, Any]] = Field(default_factory=list)
    output_for: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0
