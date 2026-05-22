from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, model_validator


class TopicDetail(BaseModel):
    """A specific topic discussed in the conversation"""
    topic: str = Field(..., description="The main topic or theme name")
    key_points: List[str] = Field(default_factory=list, description="Key points and details discussed under this topic")
    summary: Optional[str] = Field(None, description="Comprehensive summary of this topic from the conversation")
    importance_level: Optional[str] = Field(None, description="High, Medium, or Low importance level")
    bullets: Optional[List[str]] = Field(default_factory=list, description="Optional bullet points for details")
    importance: Optional[str] = Field(None, description="Alternative importance field provided by model")
    snippets: List[dict] = Field(default_factory=list, description="Relevant conversation excerpts with timestamps and speakers")
    action_items: List[str] = Field(default_factory=list, description="Action items specifically related to this topic")
    decisions_made: List[str] = Field(default_factory=list, description="Decisions made specifically about this topic")

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, values: Any) -> Any:
        if isinstance(values, dict):
            key_points = values.get("key_points")
            if isinstance(key_points, str):
                values["key_points"] = [key_points]
            elif isinstance(key_points, list):
                values["key_points"] = [str(item) for item in key_points]
            else:
                values["key_points"] = []

            bullets = values.get("bullets")
            if isinstance(bullets, str):
                values["bullets"] = [bullets]
            elif isinstance(bullets, list):
                values["bullets"] = [str(item) for item in bullets]
            else:
                values["bullets"] = []

            for field in ("action_items", "decisions_made"):
                field_value = values.get(field)
                if isinstance(field_value, str):
                    values[field] = [field_value]
                elif isinstance(field_value, list):
                    values[field] = [str(item) for item in field_value]
                else:
                    values[field] = []

            if not values.get("snippets"):
                values["snippets"] = []

            if not values.get("importance_level") and values.get("importance"):
                values["importance_level"] = values.get("importance")

        return values


class ActionItem(BaseModel):
    """A specific action item or next step"""
    task: str = Field(..., description="Clear description of the action item")
    responsible_party: Optional[str] = Field(None, description="Who is responsible (Customer, Advisor, Both)")
    timeline: Optional[str] = Field(None, description="When this should be completed")
    priority: Optional[str] = Field(None, description="High, Medium, or Low priority")

    @model_validator(mode="before")
    @classmethod
    def accept_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {
                "task": value,
                "responsible_party": None,
                "timeline": None,
                "priority": None
            }
        return value


class KeyDecision(BaseModel):
    """Important decisions made during the conversation"""
    decision: str = Field(..., description="Clear description of the decision made")
    rationale: Optional[str] = Field(None, description="Why this decision was made")
    impact: Optional[str] = Field(None, description="Expected impact or outcome of this decision")

    @model_validator(mode="before")
    @classmethod
    def accept_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {
                "decision": value,
                "rationale": None,
                "impact": None
            }
        return value


class ConversationSummary(BaseModel):
    """Comprehensive conversation summary for customer handout"""
    
    # Executive Summary
    executive_summary: str = Field(
        ..., 
        description="Comprehensive 4-6 sentence overview covering main topics, customer needs, solutions provided, and outcomes"
    )
    
    # Customer Information
    customer_profile: str = Field(
        ..., 
        description="Brief description of the customer and their situation/background"
    )
    
    # Main Topics Discussed
    topics_discussed: List[TopicDetail] = Field(
        ..., 
        description="All major topics and themes covered in the conversation"
    )
    
    # Customer Needs Analysis
    customer_needs: List[str] = Field(
        ..., 
        description="What the customer needed help with or wanted to achieve"
    )
    
    # Solutions and Advice Provided
    solutions_provided: List[str] = Field(
        ..., 
        description="Specific advice, information, and solutions offered to the customer"
    )
    
    # Action Items and Next Steps
    action_items: List[ActionItem] = Field(
        ..., 
        description="Specific tasks, follow-ups, and next steps identified"
    )
    
    # Key Decisions Made
    key_decisions: List[KeyDecision] = Field(
        ..., 
        description="Important decisions reached during the conversation"
    )
    
    # Resources and References
    resources_mentioned: List[str] = Field(
        default=[], 
        description="Any resources, websites, documents, or services mentioned"
    )
    
    # Conversation Outcome
    outcome: str = Field(
        ..., 
        description="How the conversation was resolved and what was achieved"
    )
    
    # Follow-up Required
    follow_up_required: bool = Field(
        ...,
        description="Whether additional follow-up sessions are needed"
    )
    
    follow_up_details: Optional[Union[str, Dict[str, Any]]] = Field(
        None,
        description="Details about required follow-up if any"
    )

    # Session Metadata
    session_duration: Optional[str] = Field(None, description="Duration of the conversation")
    participants: List[str] = Field(..., description="All participants in the conversation")


class LiveSummary(BaseModel):
    """Real-time summary during conversation"""
    current_summary: str = Field(..., description="Current state of conversation summary")
    topics_so_far: List[str] = Field(..., description="Topics discussed so far")
    emerging_themes: List[str] = Field(..., description="Themes that are becoming apparent")
    potential_action_items: List[str] = Field(
        default=[],
        description="Potential action items identified so far"
    )
    conversation_flow: str = Field(
        ...,
        description="How the conversation is progressing (e.g., Information gathering, Problem solving, Wrapping up)"
    )


class ExperimentRender(BaseModel):
    """Custom experiment output generated from full transcript"""

    ui_type: str = Field(..., description="Presentation style such as full_text, list, or diagram")
    content_type: str = Field(..., description="Focus of the content such as action_points or recap")
    title: str = Field(..., description="Title for the generated content")
    description: Optional[str] = Field(None, description="Introductory text or context")
    items: List[str] = Field(default_factory=list, description="List-based content when applicable")
    diagram: Optional[str] = Field(None, description="Textual representation of diagram content")
    formatted_output: Optional[str] = Field(None, description="Pre-formatted text block for direct rendering")
