from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class TranscriptEntry(BaseModel):
    session_id: str
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: float = 0.0
    speaker_confidence: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional metadata
    language: Optional[str] = None
    tags: List[str] = []
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float = 0.0
    no_speech_prob: float = 0.0
    speaker: Optional[str] = None
    speaker_confidence: float = 0.0

class TranscriptResult(BaseModel):
    session_id: str
    text: str
    language: str
    segments: List[TranscriptSegment] = []
    speakers: List[str] = []
    num_speakers: int = 0
    speech_ratio: float = 0.0
    has_speech: bool = True
    processing_time: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }