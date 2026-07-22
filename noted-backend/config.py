"""
Noted configuration — loads settings from config.yaml + secrets from .env.

Usage:
    from config import settings, prompts
    settings.server.port          # 8000
    prompts.render("live_summary.system", language="en", max_topics=4)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from services.prompt_manager import PromptManager


# ---------------------------------------------------------------------------
# Nested config dataclasses (plain objects, no Pydantic overhead)
# ---------------------------------------------------------------------------

class _ServerConfig:
    def __init__(self, d: dict):
        self.host: str = d.get("host", "0.0.0.0")
        self.port: int = d.get("port", 8000)
        self.debug: bool = d.get("debug", True)
        self.domain: str = d.get("domain", "localhost")
        self.cors_origins: List[str] = d.get("cors_origins", ["*"])


class _DatabaseConfig:
    def __init__(self, d: dict):
        self.url: str = os.getenv("DATABASE_URL", d.get("url", "sqlite+aiosqlite:///./noted.db"))


class _StorageConfig:
    def __init__(self, d: dict):
        self.upload_dir: str = d.get("upload_dir", "uploads")
        self.recordings_dir: str = d.get("recordings_dir", "recordings")
        self.data_dir: str = os.getenv("NOTED_DATA_DIR", d.get("data_dir", "knowledgebase/users_admin_data"))
        self.session_timeout: int = d.get("session_timeout", 3600)


class _WebSocketConfig:
    def __init__(self, d: dict):
        self.max_connections: int = d.get("max_connections", 50)
        self.heartbeat_interval: float = d.get("heartbeat_interval", 30.0)


class _AudioConfig:
    def __init__(self, d: dict):
        self.sample_rate: int = d.get("sample_rate", 16000)
        self.chunk_duration: float = d.get("chunk_duration", 5.0)
        self.upload_chunk_duration: float = d.get("upload_chunk_duration", 300.0)
        self.min_speech_duration: float = d.get("min_speech_duration", 0.1)
        self.max_speech_pause: float = d.get("max_speech_pause", 0.8)
        self.live_asr_max_tokens: int = d.get("live_asr_max_tokens", 100)
        self.live_diarization_window_seconds: float = d.get("live_diarization_window_seconds", 20.0)
        self.live_diarization_holdback_seconds: float = d.get("live_diarization_holdback_seconds", 1.5)
        self.live_vad_enabled: bool = d.get("live_vad_enabled", True)
        self.live_vad_frame_ms: int = d.get("live_vad_frame_ms", 30)
        self.live_vad_min_speech_ms: int = d.get("live_vad_min_speech_ms", 120)
        self.live_vad_padding_ms: int = d.get("live_vad_padding_ms", 150)
        self.live_vad_energy_threshold: float = d.get("live_vad_energy_threshold", 0.008)


class _ModelConfig:
    def __init__(self, d: dict):
        self.name: str = d.get("name", "")
        self.url: str = d.get("url", "")
        self.api_key: Optional[str] = d.get("api_key")
        self.temperature: float = d.get("temperature", 0.1)
        self.max_tokens: int = d.get("max_tokens", 8192)
        self.transcription_delay_ms: int = d.get("transcription_delay_ms", 480)
        self.hotwords: str = d.get("hotwords", "")
        self.concurrency: int = int(d.get("concurrency", 8))
        self.max_speakers: int = int(d.get("max_speakers", 2))


class _ModelsConfig:
    def __init__(self, d: dict):
        self.asr_batch = _ModelConfig(d.get("asr_batch", {}))
        self.diarization = _ModelConfig(d.get("diarization", {}))
        self.generation = _ModelConfig(d.get("generation", {}))
        self.embedding = _ModelConfig(d.get("embedding", {}))


class _VectorDBConfig:
    def __init__(self, d: dict):
        self.url: str = os.getenv("QDRANT_URL", d.get("url", "http://qdrant:6333"))
        self.host: str = os.getenv("QDRANT_HOST", d.get("host", "qdrant"))
        self.port: int = int(os.getenv("QDRANT_PORT", str(d.get("port", 6333))))
        self.grpc_port: Optional[int] = d.get("grpc_port")
        self.api_key: Optional[str] = os.getenv("QDRANT_API_KEY", d.get("api_key"))
        self.prefer_grpc: bool = d.get("prefer_grpc", False)


class _RAGConfig:
    def __init__(self, d: dict):
        self.max_keyword_matches: int = d.get("max_keyword_matches", 5)
        self.max_vector_docs: int = d.get("max_vector_docs", 5)
        self.score_threshold: float = d.get("score_threshold", 0.60)
        self.max_context_chars: int = d.get("max_context_chars", 40000)
        self.knowledgebase_csv_path: Optional[str] = d.get("knowledgebase_csv_path")


class _SummarizationConfig:
    def __init__(self, d: dict):
        self.max_topics: int = d.get("max_topics", 4)
        self.min_detail_per_topic: int = d.get("min_detail_per_topic", 80)
        self.live_refresh_seconds: int = d.get("live_refresh_seconds", 60)
        self.live_refresh_chunks: int = d.get("live_refresh_chunks", 10)
        self.auto_detect_customer_language: bool = d.get("auto_detect_customer_language", True)


class _LoggingConfig:
    def __init__(self, d: dict):
        self.enable_detailed: bool = d.get("enable_detailed", False)


class _AuthConfig:
    def __init__(self, d: dict):
        self.enabled: bool = d.get("enabled", True)
        
        self.username: str = os.getenv("NOTED_AUTH_USERNAME", os.getenv("DEMO_LOGIN", d.get("username", "demo")))
        self.password: str = os.getenv("NOTED_AUTH_PASSWORD", os.getenv("DEMO_PASSWORD", d.get("password", "demo1")))
        
        self.admin_username: str = os.getenv("ADMIN_LOGIN", d.get("admin_username", "admin"))
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", d.get("admin_password", "admin"))
        self.users_file: str = os.getenv("NOTED_AUTH_USERS_FILE", d.get("users_file", "knowledgebase/usernames_passwords/users.json"))
        self.admins_file: str = os.getenv("NOTED_AUTH_ADMINS_FILE", d.get("admins_file", "knowledgebase/usernames_passwords/admins.json"))
        
        self.secret_key: str = os.getenv("NOTED_AUTH_SECRET", d.get("secret_key", "noted-dev-secret"))
        self.token_ttl_seconds: int = int(
            os.getenv("NOTED_AUTH_TOKEN_TTL_SECONDS", str(d.get("token_ttl_seconds", 28800)))
        )
        self.role: str = d.get("role", "advisor")
        self.display_name: str = d.get("display_name", "Advisor")
        self.user_id: str = f"user:{self.username}"


# ---------------------------------------------------------------------------
# Main Settings object
# ---------------------------------------------------------------------------

class Settings:
    """Unified settings loaded from config.yaml + environment variable overrides for secrets."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.getenv("NOTED_CONFIG", str(Path(__file__).parent / "config.yaml"))

        with open(config_path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        self.server = _ServerConfig(raw.get("server", {}))
        self.database = _DatabaseConfig(raw.get("database", {}))
        self.storage = _StorageConfig(raw.get("storage", {}))
        self.websocket = _WebSocketConfig(raw.get("websocket", {}))
        self.audio = _AudioConfig(raw.get("audio", {}))
        self.models = _ModelsConfig(raw.get("models", {}))
        self.vector_db = _VectorDBConfig(raw.get("vector_db", {}))
        self.rag = _RAGConfig(raw.get("rag", {}))
        self.summarization = _SummarizationConfig(raw.get("summarization", {}))
        self.logging = _LoggingConfig(raw.get("logging", {}))
        self.auth = _AuthConfig(raw.get("auth", {}))

        # --- Environment overrides for secrets and deployment ---
        self.hf_token: Optional[str] = os.getenv("HF_TOKEN")
        self.domain: str = os.getenv("DOMAIN", self.server.domain)

        # Override model URLs/keys from env if set (docker-compose compatibility)
        gen_url = os.getenv("LLAMA_BASE_URL")
        if gen_url:
            self.models.generation.url = gen_url
        gen_key = os.getenv("LLAMA_API_KEY")
        if gen_key:
            self.models.generation.api_key = gen_key
        gen_model = os.getenv("SUMMARY_MODEL")
        if gen_model:
            self.models.generation.name = gen_model

        embed_url = os.getenv("LLAMA_EMBED_URL")
        if embed_url:
            self.models.embedding.url = embed_url
        embed_model = os.getenv("EMBEDDING_MODEL")
        if embed_model:
            self.models.embedding.name = embed_model

        asr_url = os.getenv("ASR_BATCH_URL")
        if asr_url:
            self.models.asr_batch.url = asr_url
        asr_model = os.getenv("ASR_BATCH_MODEL")
        if asr_model:
            self.models.asr_batch.name = asr_model
        asr_concurrency = os.getenv("ASR_BATCH_CONCURRENCY")
        if asr_concurrency:
            try:
                self.models.asr_batch.concurrency = max(1, int(asr_concurrency))
            except ValueError:
                pass

        diar_url = os.getenv("DIARIZATION_URL")
        if diar_url:
            self.models.diarization.url = diar_url
        diar_model = os.getenv("DIARIZATION_MODEL")
        if diar_model:
            self.models.diarization.name = diar_model
        diar_max_speakers = os.getenv("DIARIZATION_MAX_SPEAKERS")
        if diar_max_speakers:
            try:
                self.models.diarization.max_speakers = max(1, int(diar_max_speakers))
            except ValueError:
                pass

        # Audio/asr tuning overrides for production throughput tuning.
        chunk_duration = os.getenv("CHUNK_DURATION")
        if chunk_duration:
            try:
                self.audio.chunk_duration = max(1.0, float(chunk_duration))
            except ValueError:
                pass

        upload_chunk_duration = os.getenv("UPLOAD_CHUNK_DURATION")
        if upload_chunk_duration:
            try:
                self.audio.upload_chunk_duration = max(15.0, float(upload_chunk_duration))
            except ValueError:
                pass

        asr_batch_max_tokens = os.getenv("ASR_BATCH_MAX_TOKENS")
        if asr_batch_max_tokens:
            try:
                self.models.asr_batch.max_tokens = max(1, int(asr_batch_max_tokens))
            except ValueError:
                pass

        live_asr_max_tokens = os.getenv("LIVE_ASR_MAX_TOKENS")
        if live_asr_max_tokens:
            try:
                self.audio.live_asr_max_tokens = max(1, int(live_asr_max_tokens))
            except ValueError:
                pass

        live_diarization_window = os.getenv("LIVE_DIARIZATION_WINDOW_SECONDS")
        if live_diarization_window:
            try:
                self.audio.live_diarization_window_seconds = max(5.0, float(live_diarization_window))
            except ValueError:
                pass

        live_diarization_holdback = os.getenv("LIVE_DIARIZATION_HOLDBACK_SECONDS")
        if live_diarization_holdback:
            try:
                self.audio.live_diarization_holdback_seconds = max(0.0, float(live_diarization_holdback))
            except ValueError:
                pass
        # Prompts
        self._prompts_raw = raw.get("prompts", {})


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

settings = Settings()
prompts = PromptManager(settings._prompts_raw)
