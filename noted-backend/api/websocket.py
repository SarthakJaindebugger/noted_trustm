from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Any, Dict, Optional
import json
import asyncio
import logging
import os
import time
import wave
from datetime import datetime
import numpy as np

from api.auth import require_websocket_auth
from audio.processor import AudioProcessor
from api.websocket_support import (
    build_combined_payload,
    execute_control_command,
    parse_audio_chunk_payload,
)
from api.route_support import generate_and_store_summary_for_session
from utils.audio_utils import load_audio_file
from utils.text import clean_transcript_text
from models.session import SessionData, SessionStatus
from config import settings
from services.account_store import recordings_dir_for_principal

logger = logging.getLogger(__name__)

websocket_router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_connections: Dict[str, str] = {}
        from services.service_container import service_container
        self.session_manager = service_container.get_session_manager() or service_container.register_session_manager()
        self.audio_processor = None  # Initialize lazily after models are loaded
        self.session_audio_sinks: Dict[str, Dict[str, Any]] = {}

    def initialize_audio_processor(self):
        """Initialize audio processor after models are loaded"""
        if self.audio_processor is None:
            self.audio_processor = AudioProcessor()
            logger.info("Audio processor initialized")

    async def initialize_audio_processor_async(self):
        """Initialize audio processor asynchronously during startup"""
        if self.audio_processor is None:
            logger.info("Initializing audio processor asynchronously...")
            # Run in thread pool to avoid blocking startup
            loop = asyncio.get_event_loop()
            self.audio_processor = await loop.run_in_executor(
                None,
                lambda: AudioProcessor(enable_detailed_logging=settings.logging.enable_detailed)
            )
            logger.info("Audio processor initialized asynchronously")

    @staticmethod
    def _status_value(session: Optional[SessionData]) -> str:
        if not session:
            return ""
        status = getattr(session, "status", "")
        return status.value if isinstance(status, SessionStatus) else str(status)

    async def connect(
        self,
        websocket: WebSocket,
        websocket_session_id: str,
        owner_user_id: Optional[str] = None,
    ):
        await websocket.accept()
        self.active_connections[websocket_session_id] = websocket
        logger.info(f"WebSocket connection established for WebSocket session: {websocket_session_id}")

        # If the session was disconnected, mark it as active again (resume)
        session = await self.session_manager.get_session_by_websocket_id(
            websocket_session_id,
            owner_user_id=owner_user_id,
        )
        if session:
            session_name = session.session_name or session.db_id
            self.session_connections[session_name] = websocket_session_id
            current_status = self._status_value(session)
            if current_status == SessionStatus.DISCONNECTED.value:
                logger.info(f"Resuming disconnected session {session_name}")
                try:
                    await self.session_manager.set_session_status(session_name, SessionStatus.ACTIVE)
                except Exception as e:
                    logger.error(f"Failed to resume session on reconnect: {e}")

    async def disconnect(self, websocket_session_id: str, owner_user_id: Optional[str] = None):
        if websocket_session_id in self.active_connections:
            del self.active_connections[websocket_session_id]
            
            # Find the session and mark it as completed if it's still active
            session = await self.session_manager.get_session_by_websocket_id(
                websocket_session_id,
                owner_user_id=owner_user_id,
            )
            if session:
                session_name = session.session_name or session.db_id
                if self.session_connections.get(session_name) == websocket_session_id:
                    self.session_connections.pop(session_name, None)
                current_status = self._status_value(session)
                if current_status in (SessionStatus.ACTIVE.value, SessionStatus.PAUSED.value):
                    logger.info(f"WebSocket disconnected for active session {session_name} — marking as disconnected")
                    try:
                        await self.session_manager.set_session_status(session_name, SessionStatus.DISCONNECTED)
                    except Exception as e:
                        logger.error(f"Failed to update session status on disconnect: {e}")
                else:
                    logger.info(f"WebSocket closed for session {session_name} (status: {current_status})")
            else:
                stale_sessions = [
                    session_name
                    for session_name, mapped_ws_id in self.session_connections.items()
                    if mapped_ws_id == websocket_session_id
                ]
                for session_name in stale_sessions:
                    self.session_connections.pop(session_name, None)
                logger.info(f"WebSocket connection closed for unknown session (WebSocket ID: {websocket_session_id})")

    async def send_message(self, session_name: str, message: dict):
        logger.debug("Sending WebSocket message to session %s", session_name)

        websocket_session_id = self.session_connections.get(session_name)
        websocket = self.active_connections.get(websocket_session_id) if websocket_session_id else None

        if websocket:
            try:
                await websocket.send_text(json.dumps(message))
                logger.debug(
                    "Sent WebSocket message to %s via %s (type=%s)",
                    session_name,
                    websocket_session_id,
                    message.get("type", "unknown"),
                )
                return
            except Exception as e:
                logger.error(f"Failed to send WebSocket message to session {session_name}: {e}")
                if websocket_session_id:
                    self.active_connections.pop(websocket_session_id, None)
                    self.session_connections.pop(session_name, None)
                return

        logger.warning(f"No active WebSocket connection found for session: {session_name}")

    async def _get_or_create_audio_sink(
        self,
        session_id: str,
        sample_rate: int = 16000,
    ) -> Dict[str, Any]:
        sink = self.session_audio_sinks.get(session_id)
        if sink:
            return sink

        session = await self.session_manager.get_session_by_name(session_id)
        recordings_dir = recordings_dir_for_principal(
            session.owner_user_id if session else None,
            username=session.owner_username if session else None,
        )
        os.makedirs(recordings_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(recordings_dir, f"session_{session_id}_{timestamp}.wav")
        writer = wave.open(filepath, "wb")
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)

        sink = {
            "filepath": filepath,
            "writer": writer,
            "sample_rate": sample_rate,
            "chunk_count": 0,
            "sample_count": 0,
        }
        self.session_audio_sinks[session_id] = sink
        return sink

    async def _write_session_audio_chunk(
        self,
        session_id: str,
        audio_array: np.ndarray,
        sample_rate: int = 16000,
    ) -> None:
        if audio_array is None or len(audio_array) == 0:
            return

        sink = await self._get_or_create_audio_sink(session_id, sample_rate=sample_rate)
        pcm_audio = np.clip(audio_array.astype(np.float32), -1.0, 1.0)
        pcm_audio = (pcm_audio * 32767.0).astype(np.int16)
        sink["writer"].writeframes(pcm_audio.tobytes())
        sink["chunk_count"] = int(sink.get("chunk_count", 0)) + 1
        sink["sample_count"] = int(sink.get("sample_count", 0)) + int(pcm_audio.size)

    def _close_session_audio_sink(self, session_id: str) -> Optional[Dict[str, Any]]:
        sink = self.session_audio_sinks.pop(session_id, None)
        if not sink:
            return None

        writer = sink.get("writer")
        if writer is not None:
            writer.close()
        sink["writer"] = None
        return sink

    def _discard_session_audio_sink(self, session_id: str) -> None:
        sink = self._close_session_audio_sink(session_id)
        if not sink:
            return

        filepath = sink.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError as exc:
                logger.warning("Failed to remove session audio file %s: %s", filepath, exc)

    async def process_audio_chunk(self, session_id: str, audio_array: np.ndarray):
        """Process audio chunk and send results back to client"""
        try:
            logger.debug("Processing audio chunk for session %s with %s samples", session_id, len(audio_array))

            # Ensure audio processor is initialized
            if self.audio_processor is None:
                self.audio_processor = AudioProcessor(enable_detailed_logging=settings.logging.enable_detailed)

            # Persist audio incrementally instead of retaining every chunk in memory.
            if len(audio_array) > 0:
                await self._write_session_audio_chunk(session_id, audio_array, sample_rate=16000)
            
            # Send processing status update
            await self.send_message(session_id, {
                "type": "processing_status",
                "data": {"status": "processing_audio", "samples": len(audio_array)}
            })
            
            # Process audio through the live diarization + ASR pipeline
            result = await self.audio_processor.process_chunk(session_id, audio_array)
            
            if result:
                conversation_entries = result.get("conversation_entries", []) or []
                logger.debug(
                    "Audio processor returned %s conversation entries for session %s",
                    len(conversation_entries),
                    session_id,
                )
                await self.send_message(session_id, {
                    "type": "transcript_update",
                    "data": result
                })
                
                # Update session with new transcript data
                await self.session_manager.add_transcript(session_id, result)
                
            else:
                logger.info(f"Audio processor returned no result for session: {session_id}")
                # Send status update even when no result
                await self.send_message(session_id, {
                    "type": "processing_status", 
                    "data": {"status": "no_speech_detected", "message": "No speech detected in audio chunk"}
                })
                
        except Exception as e:
            logger.error(f"Error processing audio chunk for session {session_id}: {e}")
            await self.send_message(session_id, {
                "type": "error",
                "message": f"Audio processing error: {str(e)}"
            })

    async def save_session_audio(self, session_id: str) -> str:
        """Save accumulated audio for a session to file and trigger final processing"""
        try:
            sink = self.session_audio_sinks.get(session_id)
            if not sink or not int(sink.get("sample_count", 0)):
                logger.warning(f"No audio data to save for session {session_id}")
                return None

            finalized_sink = self._close_session_audio_sink(session_id)
            if not finalized_sink:
                return None

            filepath = finalized_sink.get("filepath")
            logger.info(
                "Saved %s audio chunks for %s to %s",
                finalized_sink.get("chunk_count", 0),
                session_id,
                filepath,
            )

            try:
                flush_result = await self.audio_processor.flush_live_session(session_id)
                if flush_result:
                    await self.session_manager.add_transcript(session_id, flush_result)
                if await self._finalize_live_session_from_existing_transcript(session_id):
                    logger.info("Finalized live session %s from incremental transcript without full audio reprocessing", session_id)
                else:
                    await self._process_full_session_audio(session_id, filepath)
            except Exception as processing_error:
                logger.error(f"Error processing final audio for session {session_id}: {processing_error}")

            return filepath

        except Exception as e:
            logger.error(f"Error saving session audio for {session_id}: {e}")
            self._discard_session_audio_sink(session_id)
            return None

    async def _finalize_live_session_from_existing_transcript(self, session_id: str) -> bool:
        if self.audio_processor is None:
            self.initialize_audio_processor()

        state = self.audio_processor.live_sessions.get_state(session_id)
        segments = list(state.segments or [])
        if not segments:
            return False

        started_at = time.perf_counter()
        conversation_entries = self.audio_processor.live_sessions.build_conversation_entries(segments)
        full_text = clean_transcript_text(state.full_text)
        speakers = sorted({
            str(segment.get("speaker", "")).strip()
            for segment in segments
            if str(segment.get("speaker", "")).strip()
        })

        if not conversation_entries or not full_text:
            return False

        await self.session_manager.set_session_progress(
            session_id,
            92.0,
            "summarizing",
            "Generating summary from live transcript",
        )

        combined_payload = {
            "text": full_text,
            "segments": segments,
            "speakers": speakers or ["UNKNOWN"],
            "conversation_entries": conversation_entries,
        }
        await self.session_manager.add_transcript(session_id, combined_payload, replace=True)

        summary_started_at = time.perf_counter()
        transcript_entries = await self.session_manager.get_session_transcript(session_id)
        await generate_and_store_summary_for_session(
            self.session_manager,
            session_id,
            transcript_entries=transcript_entries,
            fallback_transcript_text=full_text,
        )
        summary_ms = round((time.perf_counter() - summary_started_at) * 1000.0, 1)
        total_ms = round((time.perf_counter() - started_at) * 1000.0, 1)

        logger.info(
            "LIVE_FINALIZE_TIMING session=%s transcript_entries=%d raw_segments=%d summary_ms=%.1f total_ms=%.1f reused_incremental_transcript=true",
            session_id,
            len(conversation_entries),
            len(segments),
            summary_ms,
            total_ms,
        )
        return True


    async def _process_full_session_audio(self, session_id: str, filepath: str) -> bool:
        """Run full-session ASR and diarization for final summaries"""
        pipeline_started_at = time.perf_counter()
        if self.audio_processor is None:
            self.initialize_audio_processor()
        audio_data, sample_rate = load_audio_file(filepath, target_sr=16000)
        if audio_data.size == 0:
            logger.warning(f"Unable to load audio file for session {session_id} from {filepath}")
            return False

        duration_min = len(audio_data) / float(sample_rate or 16000) / 60.0
        await self.session_manager.set_session_progress(
            session_id,
            -1.0,  # -1 signals indeterminate progress
            "transcribing",
            f"Transcribing {duration_min:.0f} min of audio...",
        )

        processing_result = await self.audio_processor.process_full_recording(
            session_id,
            audio_data,
            sample_rate=sample_rate,
            chunk_duration=max(15.0, float(settings.audio.upload_chunk_duration or 300.0)),
        )
        transcribe_to_transcript_ms = round((time.perf_counter() - pipeline_started_at) * 1000.0, 1)

        if not processing_result:
            logger.warning(f"No processing result for full recording of session {session_id}")
            return False

        combined_payload = build_combined_payload(processing_result, audio_data, sample_rate)

        await self.session_manager.add_transcript(session_id, combined_payload, replace=True)
        await self.session_manager.set_session_progress(
            session_id,
            92.0,
            "summarizing",
            "Generating summary",
        )

        try:
            summary_started_at = time.perf_counter()
            transcript_entries = await self.session_manager.get_session_transcript(session_id)
            await generate_and_store_summary_for_session(
                self.session_manager,
                session_id,
                transcript_entries=transcript_entries,
                fallback_transcript_text=clean_transcript_text(combined_payload.get("text", "")),
            )
            summary_ms = round((time.perf_counter() - summary_started_at) * 1000.0, 1)
        except Exception as summary_error:
            logger.error(f"Failed to generate final summary for session {session_id}: {summary_error}")
            await self.session_manager.set_session_progress(
                session_id,
                97.0,
                "finalizing",
                "Transcript saved (summary warning)",
            )
            return True

        await self.session_manager.set_session_progress(
            session_id,
            99.0,
            "finalizing",
            "Saving results",
        )
        total_pipeline_ms = round((time.perf_counter() - pipeline_started_at) * 1000.0, 1)
        logger.info(
            "SESSION_PIPELINE_TIMING session=%s audio_seconds=%.1f transcribe_to_transcript_ms=%.1f summary_ms=%.1f total_ms=%.1f processing_timings=%s",
            session_id,
            len(audio_data) / float(sample_rate or 16000),
            transcribe_to_transcript_ms,
            summary_ms,
            total_pipeline_ms,
            processing_result.get("timings"),
        )
        return True

    async def shutdown(self):
        """Cleanup sessions and resources on app shutdown"""
        logger.info("ConnectionManager: Shutting down, cleaning up expired sessions...")
        
        # Close all active WebSocket connections
        for session_id, websocket in list(self.active_connections.items()):
            try:
                await websocket.close(code=1001, reason="Server shutting down")
                logger.info(f"Closed WebSocket for session {session_id}")
            except Exception as e:
                logger.error(f"Error closing WebSocket for session {session_id}: {e}")
        
        self.active_connections.clear()
        self.session_connections.clear()
        for session_id in list(self.session_audio_sinks.keys()):
            self._close_session_audio_sink(session_id)
        
        # Shutdown audio processor if it exists
        if self.audio_processor:
            await self.audio_processor.shutdown()
        
        # Shutdown session manager
        await self.session_manager.shutdown()  # This will clean up DB & cache
        logger.info("ConnectionManager: Shutdown complete")

manager = ConnectionManager()

@websocket_router.websocket("/audio/{websocket_session_id}")
async def websocket_endpoint(websocket: WebSocket, websocket_session_id: str):
    try:
        current_user = await require_websocket_auth(websocket)
    except Exception as exc:
        await websocket.close(code=4401, reason=str(getattr(exc, "detail", "Unauthorized")))
        return

    session = await manager.session_manager.get_session_by_websocket_id(
        websocket_session_id,
        owner_user_id=current_user.id,
    )
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await manager.connect(websocket, websocket_session_id, owner_user_id=current_user.id)
    
    # Find the actual session by WebSocket session ID
    try:
        while True:
            try:
                # Receive audio data from client
                data = await asyncio.wait_for(websocket.receive(), timeout=5)

                new_chunk = parse_audio_chunk_payload(data)
                if new_chunk is None:
                    logger.warning(
                        "Ignoring invalid audio frame for session %s",
                        session.session_name,
                    )
                    continue

                # Process audio chunk asynchronously using the session name (not WebSocket ID)
                await manager.process_audio_chunk(session.session_name, new_chunk)
                
            except asyncio.TimeoutError:
                # Timeout is normal when no audio is being sent
                continue
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        await manager.disconnect(websocket_session_id, owner_user_id=current_user.id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket_session_id, owner_user_id=current_user.id)

@websocket_router.websocket("/control/{session_id}")
async def control_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for session control (pause, resume, stop)"""
    try:
        current_user = await require_websocket_auth(websocket)
    except Exception as exc:
        await websocket.close(code=4401, reason=str(getattr(exc, "detail", "Unauthorized")))
        return

    session = await manager.session_manager.get_session_by_name(
        session_id,
        owner_user_id=current_user.id,
    )
    if not session:
        session = await manager.session_manager.get_session_by_db_id(
            session_id,
            owner_user_id=current_user.id,
        )
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            command = data.get("command")

            response, should_close = await execute_control_command(
                manager.session_manager,
                session.session_name,
                command,
            )
            await websocket.send_text(json.dumps(response))
            if should_close:
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Control WebSocket error: {e}")
