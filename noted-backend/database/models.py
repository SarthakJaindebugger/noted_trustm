from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.connection import Base
import uuid

class Session(Base):
    __tablename__ = "sessions"
    
    session_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(50), default="active")
    session_name = Column(String, unique=True, index=True, nullable=True)
    websocket_session_id = Column(String, nullable=True, index=True)  # For WebSocket connections
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Session metadata
    owner_user_id = Column(String(255), nullable=True, index=True)
    owner_username = Column(String(255), nullable=True)
    client_name = Column(String(255), nullable=True)
    advisor_name = Column(String(255), nullable=True) 
    service_type = Column(String(255), nullable=True)
    advisor_notes = Column(Text, nullable=True)
    
    # Processing stats
    total_duration = Column(Float, default=0.0)
    speech_duration = Column(Float, default=0.0)
    processing_time = Column(Float, default=0.0)
    
    # Additional metadata
    metadata_json = Column(JSON, nullable=True)
    
    # Relationships
    transcripts = relationship("TranscriptEntry", back_populates="session", cascade="all, delete-orphan")
    speakers = relationship("Speaker", back_populates="session", cascade="all, delete-orphan")

class TranscriptEntry(Base):
    __tablename__ = "transcript_entries"
    __table_args__ = (
        Index("ix_transcript_entries_session_chunk_start", "session_id", "chunk_index", "start_time"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, index=True)
    
    # Transcript content
    speaker = Column(String(255), nullable=False)
    text = Column(Text, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    
    # Confidence scores
    confidence = Column(Float, default=0.0)
    speaker_confidence = Column(Float, default=0.0)
    
    # Metadata
    language = Column(String(10), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    chunk_index = Column(Integer, default=0)  # Order within session
    
    # Additional data
    tags = Column(JSON, nullable=True)  # Store tags as JSON array
    metadata_json = Column(JSON, nullable=True)
    
    # Relationships
    session = relationship("Session", back_populates="transcripts")

class Speaker(Base):
    __tablename__ = "speakers"
    
    session_id = Column(String(255), ForeignKey("sessions.session_id"), primary_key=True, nullable=False)
    
    # Speaker info
    speaker_label = Column(String(255), nullable=False)  # e.g., "Customer", "Advisor", "Speaker_01"
    speaker_role = Column(String(255), nullable=True)    # e.g., "client", "advisor"
    
    # Statistics
    total_speaking_time = Column(Float, default=0.0)
    word_count = Column(Integer, default=0)
    avg_confidence = Column(Float, default=0.0)
    
    # Timestamps
    first_appearance = Column(DateTime(timezone=True), server_default=func.now())
    last_appearance = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("Session", back_populates="speakers")

class SessionStats(Base):
    __tablename__ = "session_stats"

    session_id = Column(String(255), ForeignKey("sessions.session_id"), unique=True, nullable=False, primary_key=True)
    
    # Processing statistics
    total_chunks_processed = Column(Integer, default=0)
    total_audio_duration = Column(Float, default=0.0)
    total_speech_duration = Column(Float, default=0.0)
    total_processing_time = Column(Float, default=0.0)
    average_processing_time = Column(Float, default=0.0)
    
    # Content statistics
    speakers_identified = Column(Integer, default=0)
    languages_detected = Column(JSON, nullable=True)  # Array of language codes
    total_words = Column(Integer, default=0)
    avg_confidence = Column(Float, default=0.0)
    
    # Quality metrics
    speech_to_silence_ratio = Column(Float, default=0.0)
    speaker_switch_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SessionSummary(Base):
    __tablename__ = "session_summaries"
    
    session_id = Column(String(255), ForeignKey("sessions.session_id"), unique=True, nullable=False, primary_key=True)
    
    # Summary content
    overview = Column(Text, nullable=True)
    action_items = Column(JSON, nullable=True)  # Array of action items
    topics_discussed = Column(JSON, nullable=True)  # Array of topics
    related_services = Column(JSON, nullable=True)  # Array of service objects
    output_for = Column(JSON, nullable=True)  # Array of output categories
    
    # AI-generated metadata
    confidence_score = Column(Float, default=0.0)
    summary_model = Column(String(255), nullable=True)  # Which AI model generated this
    
    # Timestamps
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CRMForm(Base):
    __tablename__ = "crm_forms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, index=True)

    # Encounter details
    encounter_date = Column(DateTime(timezone=True), server_default=func.now())
    encounter_type = Column(String(100), nullable=True)  # e.g. "in-person", "phone", "video"
    advisor_name = Column(String(255), nullable=True)
    client_name = Column(String(255), nullable=True)
    client_id = Column(String(100), nullable=True)

    # Content (auto-filled from summary)
    topics_discussed = Column(JSON, nullable=True)
    action_items = Column(JSON, nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    follow_up_notes = Column(Text, nullable=True)
    outcome = Column(String(255), nullable=True)  # e.g. "resolved", "follow-up needed", "referred"
    referrals = Column(JSON, nullable=True)  # services/departments referred to
    notes = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="draft")  # draft, submitted
    language = Column(String(10), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AudioChunk(Base):
    __tablename__ = "audio_chunks"
    
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, primary_key=True)
    
    # Chunk metadata
    chunk_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    
    # Audio properties
    sample_rate = Column(Integer, default=16000)
    channels = Column(Integer, default=1)
    has_speech = Column(Boolean, default=False)
    speech_ratio = Column(Float, default=0.0)
    
    # Processing info
    vad_confidence = Column(Float, default=0.0)
    processing_time = Column(Float, default=0.0)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # File storage (optional - for debugging/replay)
    audio_file_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
