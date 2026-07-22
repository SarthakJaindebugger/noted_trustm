import asyncio
import json
import re

from typing import List, Dict, Optional, Tuple
import numpy as np
from openai import OpenAI
import time

from collections import deque
import threading
import logging
from utils.audio_utils import convert_audio_format

from config import settings, prompts

logger = logging.getLogger(__name__)

def _build_openai_client():
    return OpenAI(
        base_url=settings.models.generation.url,
        api_key=settings.models.generation.api_key or "none",
    )

class ConversationState:
    def __init__(self):
        # segments: list of {start,end,text,confidence,no_speech_prob, speaker?}
        self.sessions: Dict[str, Dict] = {}

    def ensure(self, session_id: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "segments": [],
                "full_text": "",
                "last_summary": None,
                "topics": [],
                "audio_seconds": 0.0
            }

    def add_segments(self, session_id: str, segments: List[Dict]):
        self.ensure(session_id)
        self.sessions[session_id]["segments"].extend(segments)
        # Keep full text smallish for prompts
        full = " ".join(seg["text"] for seg in self.sessions[session_id]["segments"])
        # Optional cap to prevent runaway context (keep last ~25k chars)
        self.sessions[session_id]["full_text"] = full[-25000:]

    def add_audio_dur(self, session_id: str, seconds: float):
        self.ensure(session_id)
        self.sessions[session_id]["audio_seconds"] += seconds

    def get_full_text(self, session_id: str) -> str:
        self.ensure(session_id)
        return self.sessions[session_id]["full_text"]

    def get_segments(self, session_id: str) -> List[Dict]:
        self.ensure(session_id)
        return self.sessions[session_id]["segments"]

    def set_summary(self, session_id: str, summary: Dict):
        self.ensure(session_id)
        self.sessions[session_id]["last_summary"] = summary
        self.sessions[session_id]["topics"] = summary.get("topics", [])

    def get_summary(self, session_id: str) -> Optional[Dict]:
        self.ensure(session_id)
        return self.sessions[session_id]["last_summary"]

_client = None
def _client_once():
    global _client
    if _client is None:
        _client = _build_openai_client()
    return _client

def _chat_completion(model: str, messages: List[Dict], temperature: float = 0.2, max_tokens: int = 800):
    client = _client_once()
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

class Summarizer:
    def __init__(self, model: str = None):
        self.model = model or settings.models.generation.name

    @staticmethod
    def _safe_json_parse(text: str) -> Dict:
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to repair truncated JSON by closing open braces/brackets
            repaired = text
            open_braces = repaired.count("{") - repaired.count("}")
            open_brackets = repaired.count("[") - repaired.count("]")
            # Trim trailing incomplete key/value (after last comma or colon)
            for trim_char in (",", ":"):
                last = repaired.rfind(trim_char)
                if last > 0 and last > len(repaired) - 50:
                    candidate = repaired[:last]
                    candidate += "]" * (candidate.count("[") - candidate.count("]"))
                    candidate += "}" * (candidate.count("{") - candidate.count("}"))
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
            # Brute-force close
            repaired += '"]' * max(0, open_brackets) + "}" * max(0, open_braces)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return {"summary": text, "topics": []}

    async def summarize_conversation(self, text: str) -> Dict:
        if not text.strip():
            return {"summary": "No content yet.", "topics": []}

        sys = prompts.render("chunk_summary.system")
        user = prompts.render("chunk_summary.user", transcript=text)

        def _run():
            resp = _chat_completion(self.model, [
                {"role": "system", "content": sys},
                {"role": "user", "content": user}
            ], temperature=0.2, max_tokens=700)
            from utils.text import strip_think_tags
            return strip_think_tags(resp.choices[0].message.content or "")

        out = await asyncio.to_thread(_run)
        return self._safe_json_parse(out)

    async def summarize_topic(self, topic: str, segments: List[Dict]) -> Dict:
        """
        Use embedding-based semantic retrieval to find relevant chunks,
        then ask the LLM to summarize the topic from those chunks.
        Returns JSON: {topic, summary, snippets:[{start,end,text,speaker}]}
        """
        if not segments:
            return {"topic": topic, "summary": f"No content found for '{topic}'.", "snippets": []}

        from services.service_container import service_container
        embedding_service = service_container.get_embedding_service()

        # Group segments into ~200-word chunks for meaningful context
        chunks = _chunk_segments(segments, target_words=200)
        if not chunks:
            return {"topic": topic, "summary": f"No content found for '{topic}'.", "snippets": []}

        # Build text for each chunk
        chunk_texts = [c["text"] for c in chunks]
        topic_keywords = [
            tok for tok in re.findall(r"[a-zA-Z0-9]+", topic.lower())
            if len(tok) > 2 and tok not in {"the", "and", "for", "with", "from", "this", "that", "what", "when", "where", "how"}
        ]
        keyword_scores = []
        for text in chunk_texts:
            lowered = text.lower()
            keyword_scores.append(sum(lowered.count(kw) for kw in topic_keywords))

        # Embed topic + all chunks in one batch, then cosine-similarity pick top-k
        semantic_scores: List[float] = [0.0] * len(chunks)
        try:
            all_texts = [topic] + chunk_texts
            all_embeddings = await asyncio.to_thread(embedding_service.embed_batch, all_texts)
            topic_vec = np.array(all_embeddings[0])
            chunk_vecs = np.array(all_embeddings[1:])

            # Cosine similarity
            norms = np.linalg.norm(chunk_vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1e-9
            similarities = (chunk_vecs @ topic_vec) / (norms.flatten() * (np.linalg.norm(topic_vec) + 1e-9))
            semantic_scores = [float(v) for v in similarities]
        except Exception as e:
            logger.warning("Embedding-based retrieval failed, using keyword-only ranking: %s", e)

        scored_chunks = []
        for idx, chunk in enumerate(chunks):
            semantic = semantic_scores[idx] if idx < len(semantic_scores) else 0.0
            keyword = float(keyword_scores[idx]) if idx < len(keyword_scores) else 0.0
            combined = semantic + (0.12 * keyword)
            scored_chunks.append((combined, idx, chunk))

        scored_chunks.sort(key=lambda item: item[0], reverse=True)

        max_chunks_for_prompt = 8
        max_chars_per_chunk = 750
        max_context_chars = 5000
        selected_ranked = []
        context_chars = 0

        for _, _, chunk in scored_chunks:
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue

            bounded_text = text[:max_chars_per_chunk]
            block = f"[{chunk['speaker']} {chunk['start']:.1f}-{chunk['end']:.1f}] {bounded_text}"

            if context_chars + len(block) > max_context_chars and selected_ranked:
                continue

            selected_ranked.append(chunk)
            context_chars += len(block)
            if len(selected_ranked) >= max_chunks_for_prompt:
                break

        if not selected_ranked:
            selected_ranked = chunks[: min(4, len(chunks))]

        relevant_chunks = sorted(
            selected_ranked,
            key=lambda c: (float(c.get("start", 0) or 0.0), float(c.get("end", 0) or 0.0))
        )

        snippets_text = "\n".join(
            f"[{c['speaker']} {c['start']:.1f}-{c['end']:.1f}] {str(c['text'])[:max_chars_per_chunk]}"
            for c in relevant_chunks
        )
        logger.info(
            "Topic summary retrieval: topic='%s' chunks_total=%d selected=%d context_chars=%d",
            topic,
            len(chunks),
            len(relevant_chunks),
            len(snippets_text),
        )
        sys = prompts.render("topic_summary.system")
        user = prompts.render("topic_summary.user", topic=topic, snippets_text=snippets_text)

        def _run():
            resp = _chat_completion(self.model, [
                {"role": "system", "content": sys},
                {"role": "user", "content": user}
            ], temperature=0.1, max_tokens=600)
            from utils.text import strip_think_tags
            return strip_think_tags(resp.choices[0].message.content or "")

        out = await asyncio.to_thread(_run)
        data = self._safe_json_parse(out)

        # If model didn't return snippets, inject from retrieved chunks
        if not data.get("snippets"):
            data["snippets"] = [
                {"start": float(c["start"]), "end": float(c["end"]),
                 "speaker": c.get("speaker", "UNK"), "quote": c["text"][:200]}
                for c in relevant_chunks[:6]
            ]
        return data


def _chunk_segments(segments: List[Dict], target_words: int = 200) -> List[Dict]:
    """Group consecutive segments into chunks of ~target_words words each."""
    chunks = []
    current_texts = []
    current_speakers = []
    current_start = 0.0
    current_end = 0.0
    current_word_count = 0

    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        words = len(text.split())
        speaker = seg.get("speaker", "UNK")

        if current_word_count == 0:
            current_start = float(seg.get("start", 0))

        current_texts.append(f"{speaker}: {text}")
        current_speakers.append(speaker)
        current_end = float(seg.get("end", 0))
        current_word_count += words

        if current_word_count >= target_words:
            # Pick most frequent speaker as chunk speaker
            from collections import Counter
            most_common = Counter(current_speakers).most_common(1)[0][0]
            chunks.append({
                "text": " ".join(current_texts),
                "speaker": most_common,
                "start": current_start,
                "end": current_end,
            })
            current_texts = []
            current_speakers = []
            current_word_count = 0

    # Flush remaining
    if current_texts:
        from collections import Counter
        most_common = Counter(current_speakers).most_common(1)[0][0]
        chunks.append({
            "text": " ".join(current_texts),
            "speaker": most_common,
            "start": current_start,
            "end": current_end,
        })

    return chunks


class AudioChunker:
    """Manages audio buffering and chunking for real-time processing using efficient numpy operations"""

    def __init__(self):
        self.session_buffers: Dict[str, np.ndarray] = {}
        self.session_write_positions: Dict[str, int] = {}
        self.session_total_written: Dict[str, int] = {}
        self.session_total_processed: Dict[str, int] = {}
        self.session_locks: Dict[str, threading.Lock] = {}
        self.chunk_size = int(settings.audio.sample_rate * settings.audio.chunk_duration)  # e.g. 5s
        self.max_buffer_size = settings.audio.sample_rate * 60  # 60 seconds max
        logger.info(f"AudioChunker initialized with {settings.audio.chunk_duration}s chunks")

    
    def add_to_buffer(self, session_id: str, audio_data: np.ndarray):
        """Add numpy array to circular buffer efficiently using numpy operations."""
        if session_id not in self.session_buffers:
            # Initialize circular buffer with zeros
            self.session_buffers[session_id] = np.zeros(self.max_buffer_size, dtype=np.float32)
            self.session_write_positions[session_id] = 0
            self.session_total_written[session_id] = 0
            self.session_total_processed[session_id] = 0
            self.session_locks[session_id] = threading.Lock()

        with self.session_locks[session_id]:
            write_pos = self.session_write_positions[session_id]
            data_len = len(audio_data)
            buffer = self.session_buffers[session_id]

            # Handle wrap-around for circular buffer
            if write_pos + data_len <= len(buffer):
                # No wrap-around needed
                buffer[write_pos:write_pos + data_len] = audio_data
            else:
                # Handle wrap-around
                first_part_len = len(buffer) - write_pos
                buffer[write_pos:] = audio_data[:first_part_len]
                remaining = audio_data[first_part_len:]
                if len(remaining) > 0:
                    buffer[:len(remaining)] = remaining

            # Update write position with wrap-around
            self.session_write_positions[session_id] = (write_pos + data_len) % len(buffer)
            self.session_total_written[session_id] += data_len
    
    def should_process(self, session_id: str) -> bool:
        """True when a full non-overlapping chunk of new audio is available."""
        if session_id not in self.session_buffers:
            return False

        with self.session_locks[session_id]:
            total_written = self.session_total_written.get(session_id, 0)
            total_processed = self.session_total_processed.get(session_id, 0)
            return (total_written - total_processed) >= self.chunk_size
    
    def get_processing_chunk(self, session_id: str) -> Optional[np.ndarray]:
        """Get the next unprocessed chunk from the circular buffer (no overlap)."""
        if session_id not in self.session_buffers:
            return None

        with self.session_locks[session_id]:
            buffer = self.session_buffers[session_id]
            total_written = self.session_total_written.get(session_id, 0)
            total_processed = self.session_total_processed.get(session_id, 0)

            if (total_written - total_processed) < self.chunk_size:
                return None

            # If the reader fell behind the ring buffer capacity, skip to oldest available sample.
            earliest_available = total_written - len(buffer)
            if total_processed < earliest_available:
                logger.warning(
                    "AudioChunker overrun for session %s: dropping %.2fs of stale audio",
                    session_id,
                    (earliest_available - total_processed) / float(settings.audio.sample_rate),
                )
                total_processed = earliest_available
                self.session_total_processed[session_id] = total_processed
                if (total_written - total_processed) < self.chunk_size:
                    return None

            start_abs = total_processed
            end_abs = start_abs + self.chunk_size
            start_pos = start_abs % len(buffer)
            end_pos = end_abs % len(buffer)

            if start_pos < end_pos:
                chunk_data = buffer[start_pos:end_pos].copy()
            else:
                first_part = buffer[start_pos:].copy()
                second_part = buffer[:end_pos].copy()
                chunk_data = np.concatenate([first_part, second_part])

            self.session_total_processed[session_id] = end_abs
            return chunk_data

    def drain_pending_audio(self, session_id: str) -> Optional[np.ndarray]:
        """Return all currently unprocessed audio for final live-session flushing."""
        if session_id not in self.session_buffers:
            return None

        with self.session_locks[session_id]:
            buffer = self.session_buffers[session_id]
            total_written = self.session_total_written.get(session_id, 0)
            total_processed = self.session_total_processed.get(session_id, 0)
            pending = total_written - total_processed
            if pending <= 0:
                return None

            if pending > len(buffer):
                total_processed = total_written - len(buffer)
                pending = len(buffer)
                self.session_total_processed[session_id] = total_processed

            start_pos = total_processed % len(buffer)
            end_pos = total_written % len(buffer)
            if start_pos < end_pos:
                chunk_data = buffer[start_pos:end_pos].copy()
            else:
                first_part = buffer[start_pos:].copy()
                second_part = buffer[:end_pos].copy()
                chunk_data = np.concatenate([first_part, second_part]) if len(second_part) else first_part

            self.session_total_processed[session_id] = total_written
            return chunk_data
    
    def get_latest_chunk(self, session_id: str, duration: float = None) -> Optional[np.ndarray]:
        """
        Get the latest audio data without removing from buffer
        
        Args:
            session_id: Session identifier
            duration: Duration in seconds (default: chunk_duration)
            
        Returns:
            Latest audio chunk or None
        """
        if session_id not in self.session_buffers:
            return None
        
        duration = duration or settings.audio.chunk_duration
        samples_needed = int(settings.audio.sample_rate * duration)
        
        with self.session_locks[session_id]:
            buffer = self.session_buffers[session_id]
            
            if len(buffer) < samples_needed:
                # Return all available data
                return np.array(list(buffer), dtype=np.float32) if buffer else None
            
            # Get latest N samples
            latest_samples = list(buffer)[-samples_needed:]
            return np.array(latest_samples, dtype=np.float32)
    
    def get_buffer_size(self, session_id: str) -> int:
        """Get number of pending (unprocessed) samples for session."""
        if session_id not in self.session_buffers:
            return 0

        with self.session_locks[session_id]:
            total_written = self.session_total_written.get(session_id, 0)
            total_processed = self.session_total_processed.get(session_id, 0)
            return max(0, total_written - total_processed)
    
    def get_buffer_duration(self, session_id: str) -> float:
        """Get buffer duration in seconds"""
        buffer_size = self.get_buffer_size(session_id)
        return buffer_size / settings.audio.sample_rate
    
    def clear_buffer(self, session_id: str):
        """Clear buffer for session"""
        if session_id in self.session_buffers:
            with self.session_locks[session_id]:
                self.session_buffers[session_id].fill(0)
                self.session_write_positions[session_id] = 0
                self.session_total_written[session_id] = 0
                self.session_total_processed[session_id] = 0
    
    def cleanup_session(self, session_id: str):
        """Clean up session resources"""
        if session_id in self.session_buffers:
            del self.session_buffers[session_id]

        if session_id in self.session_write_positions:
            del self.session_write_positions[session_id]

        if session_id in self.session_total_written:
            del self.session_total_written[session_id]

        if session_id in self.session_total_processed:
            del self.session_total_processed[session_id]

        if session_id in self.session_locks:
            del self.session_locks[session_id]

        logger.info(f"Cleaned up audio buffer for session {session_id}")
    
    def get_session_stats(self, session_id: str) -> Dict:
        """Get statistics for session buffer"""
        if session_id not in self.session_buffers:
            return {"exists": False}

        with self.session_locks[session_id]:
            total_written = self.session_total_written.get(session_id, 0)
            total_processed = self.session_total_processed.get(session_id, 0)
            pending_samples = max(0, total_written - total_processed)
            duration = pending_samples / settings.audio.sample_rate

            return {
                "exists": True,
                "buffer_size": pending_samples,
                "duration_seconds": duration,
                "chunks_ready": pending_samples // self.chunk_size,
                "chunk_size": self.chunk_size,
                "chunk_duration": settings.audio.chunk_duration
            }
    
    def has_session(self, session_id: str) -> bool:
        """Check if session exists"""
        return session_id in self.session_buffers
    
    def get_all_sessions(self) -> list:
        """Get list of all active session IDs"""
        return list(self.session_buffers.keys())
