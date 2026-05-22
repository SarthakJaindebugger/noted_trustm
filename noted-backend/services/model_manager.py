import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class ModelManager:
    """Singleton for externally served ASR and diarization services."""

    _instance: Optional['ModelManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialized = True

    async def initialize_models(self):
        logger.info("Model manager ready (ASR and diarization handled by external services)")

    def get_model_status(self) -> Dict[str, str]:
        return {"asr": "external", "diarization": "external"}

    async def cleanup_models(self):
        logger.info("Model cleanup completed")


# Global instance
model_manager = ModelManager()
