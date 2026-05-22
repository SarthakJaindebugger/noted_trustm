from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ServiceDocumentPayload(BaseModel):
    """
    Structured payload for the Finnish service knowledge base.

    The combined_text field concatenates the most relevant text attributes that
    are sent to the embedding model.
    """

    record_id: str = Field(..., description="Deterministic identifier used as the Qdrant point id.")
    service_name: str
    description: Optional[str] = None
    mini_description: Optional[str] = None
    short_description: Optional[str] = None
    service_link: Optional[str] = None
    other_links: List[str] = Field(default_factory=list)
    combined_text: str = Field(..., description="Text that is embedded for similarity search.")
    date: Optional[str] = None
    source: str = "knowledgebase/suomi_services.csv"

    def to_payload(self) -> Dict[str, object]:
        """Return a serialisable payload for Qdrant."""
        data = self.dict()
        # record_id is stored as Qdrant point id, no need to duplicate
        data.pop("record_id", None)
        # Exclude empty optional fields to keep payload compact
        return {key: value for key, value in data.items() if value not in (None, [], "")}
