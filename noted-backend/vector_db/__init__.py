"""
Helpers for connecting to and managing Qdrant vector collections.
"""

from .client import get_qdrant_client  # noqa: F401
from .collections import (  # noqa: F401
    KNOWLEDGEBASE_COLLECTION,
    ensure_knowledgebase_collection,
)
