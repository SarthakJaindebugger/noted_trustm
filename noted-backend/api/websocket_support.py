from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import settings
from utils.text import clean_transcript_text


def parse_audio_chunk_payload(message: Dict[str, Any]) -> Optional[np.ndarray]:
    """Convert a websocket frame into a float32 audio chunk when valid."""
    audio_data = message.get("bytes")
    if not audio_data or len(audio_data) % 4 != 0:
        return None
    return np.frombuffer(audio_data, dtype=np.float32)


async def execute_control_command(session_manager, session_id: str, command: str) -> Tuple[Dict[str, str], bool]:
    """Apply a control command and return the websocket response plus close flag."""
    if command == "pause":
        await session_manager.pause_session(session_id)
        return {"type": "status", "message": "Session paused"}, False

    if command == "resume":
        await session_manager.resume_session(session_id)
        return {"type": "status", "message": "Session resumed"}, False

    if command == "stop":
        await session_manager.end_session(session_id)
        return {"type": "status", "message": "Session ended"}, True

    return {"type": "error", "message": f"Unknown command: {command}"}, False


def build_combined_payload(
    processing_result: Dict[str, Any],
    audio_data,
    sample_rate: int,
) -> Dict[str, Any]:
    combined = processing_result.get("combined", {})
    combined_payload = {
        **combined,
        "language": processing_result.get("language", "unknown"),
        "language_confidence": processing_result.get("language_confidence", 0.0),
    }

    conversation_entries = combined_payload.get("conversation_entries", []) or []
    if conversation_entries:
        combined_payload["start_time"] = conversation_entries[0].get("start_time", 0.0)
        combined_payload["end_time"] = conversation_entries[-1].get("end_time", 0.0)
    else:
        total_duration = len(audio_data) / float(sample_rate or 16000)
        combined_payload["start_time"] = 0.0
        combined_payload["end_time"] = total_duration

    combined_payload.setdefault("confidence", 0.9)
    combined_payload.setdefault("speaker_confidence", 0.8)
    return combined_payload


async def generate_topic_summary_payloads(
    audio_processor,
    final_summary: Dict[str, Any],
    transcript_text: str = "",
) -> List[Dict[str, Any]]:
    """Create structured topic summaries combining LLM topic analysis and final summary data."""
    topics_raw = final_summary.get("topics_discussed") or []

    normalized_topic_map: Dict[str, Dict[str, Any]] = {}
    for idx, topic_entry in enumerate(topics_raw):
        topic_name = None
        topic_detail = None

        if isinstance(topic_entry, dict):
            topic_detail = topic_entry
            topic_name = topic_entry.get("topic") or topic_entry.get("name")

        if not topic_name:
            topic_name = str(topic_entry).strip()

        if not topic_name:
            topic_name = f"Topic {idx + 1}"

        normalized_key = topic_name.lower().strip()
        if normalized_key not in normalized_topic_map:
            normalized_topic_map[normalized_key] = {
                "topic_name": topic_name,
                "detail": topic_detail,
            }

    if not normalized_topic_map:
        default_entry = {
            "topic": "General Discussion",
            "summary": final_summary.get("executive_summary", "Session summary unavailable."),
            "key_points": final_summary.get("customer_needs", []),
            "action_items": format_action_items_for_topic(final_summary.get("action_items", [])),
            "decisions_made": stringify_collection(final_summary.get("key_decisions", [])),
            "snippets": [],
            "related_services": [],
        }
        default_entry["related_services"] = match_topic_services(
            audio_processor,
            default_entry,
            transcript_text=transcript_text,
            max_results=3,
        )
        return [default_entry]

    topic_payloads: List[Dict[str, Any]] = []
    for topic_meta in normalized_topic_map.values():
        merged = merge_topic_summary_data(
            topic_meta["topic_name"],
            topic_meta["detail"],
            topic_meta["detail"],
        )
        merged["related_services"] = match_topic_services(
            audio_processor,
            merged,
            transcript_text=transcript_text,
            max_results=3,
        )
        topic_payloads.append(merged)

    return topic_payloads


def merge_topic_summary_data(
    fallback_name: str,
    topic_detail: Optional[Dict[str, Any]],
    topic_summary_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge topic detail from final summary with topic-specific LLM analysis."""
    entry: Dict[str, Any] = {
        "topic": fallback_name,
        "key_points": [],
        "bullets": [],
        "snippets": [],
        "action_items": [],
        "decisions_made": [],
    }

    if topic_detail and isinstance(topic_detail, dict):
        entry["topic"] = topic_detail.get("topic") or topic_detail.get("name") or fallback_name
        key_points = topic_detail.get("key_points") or topic_detail.get("bullets") or []
        entry["key_points"] = [str(point) for point in key_points if point]
        bullets = topic_detail.get("bullets") or []
        entry["bullets"] = [str(point) for point in bullets if point]

        importance = topic_detail.get("importance_level") or topic_detail.get("importance")
        if importance:
            entry["importance"] = importance
        if topic_detail.get("summary"):
            entry["summary"] = topic_detail.get("summary")
        if topic_detail.get("snippets"):
            entry["snippets"] = topic_detail.get("snippets") or []
        if topic_detail.get("action_items"):
            entry["action_items"] = stringify_collection(topic_detail.get("action_items", []))
        if topic_detail.get("decisions_made"):
            entry["decisions_made"] = stringify_collection(topic_detail.get("decisions_made", []))

    if topic_summary_data and isinstance(topic_summary_data, dict):
        entry["topic"] = topic_summary_data.get("topic") or entry["topic"]
        summary_text = topic_summary_data.get("summary")
        if summary_text and not entry.get("summary"):
            entry["summary"] = summary_text

        summary_key_points = topic_summary_data.get("key_points")
        if summary_key_points:
            entry["key_points"] = [str(point) for point in summary_key_points if point]

        entry["snippets"] = topic_summary_data.get("snippets", []) or []
        entry["action_items"] = stringify_collection(topic_summary_data.get("action_items", []))
        entry["decisions_made"] = stringify_collection(topic_summary_data.get("decisions_made", []))

    if "summary" not in entry:
        entry["summary"] = fallback_topic_summary(entry["topic"], entry["key_points"])

    entry["key_points"] = [str(point) for point in entry.get("key_points", []) if point]
    entry["bullets"] = [str(point) for point in entry.get("bullets", []) if point]
    entry["action_items"] = [str(item) for item in entry.get("action_items", []) if item]
    entry["decisions_made"] = [str(item) for item in entry.get("decisions_made", []) if item]

    if not entry.get("snippets"):
        entry["snippets"] = []
    if not entry.get("related_services"):
        entry["related_services"] = []

    return entry


def match_topic_services(
    audio_processor,
    topic_payload: Dict[str, Any],
    transcript_text: str = "",
    max_results: int = 3,
) -> List[Dict[str, Any]]:
    """Find service references for one topic using semantic + keyword matching."""
    if not audio_processor:
        return []

    topic_name = str(topic_payload.get("topic") or "").strip()
    summary = str(topic_payload.get("summary") or "").strip()
    key_points = topic_payload.get("key_points") or []
    key_points_text = " ".join(str(point) for point in key_points[:5] if point)

    context_parts = [topic_name, summary, key_points_text]
    context_text = " ".join(part for part in context_parts if part).strip()
    if not context_text:
        context_text = clean_transcript_text(transcript_text)[:1200]
    if not context_text:
        return []

    semantic_candidates: List[Dict[str, Any]] = []
    keyword_candidates: List[Dict[str, Any]] = []

    try:
        if getattr(audio_processor, "embedding_service", None):
            scored_points = audio_processor.embedding_service.search_knowledgebase(
                context_text,
                limit=max(6, max_results * 2),
                score_threshold=settings.rag.score_threshold,
            )
            for point in scored_points:
                payload = point.payload or {}
                name = str(payload.get("service_name") or "").strip()
                if not name:
                    continue
                semantic_candidates.append({
                    "name": name,
                    "url": str(payload.get("service_link") or "").strip(),
                    "score": float(getattr(point, "score", 0.0) or 0.0),
                    "source": "semantic",
                })
    except Exception:
        pass

    try:
        keyword_matches = audio_processor._collect_service_keyword_matches(
            context_text,
            limit=max(6, max_results * 2),
        )
        for match in keyword_matches:
            name = str(match.get("service_name") or "").strip()
            if not name:
                continue
            keyword_candidates.append({
                "name": name,
                "url": str(match.get("service_link") or "").strip(),
                "score": float(match.get("match_ratio", 0.0) or 0.0),
                "source": "keyword",
            })
    except Exception:
        pass

    merged: Dict[tuple, Dict[str, Any]] = {}
    for candidate in semantic_candidates + keyword_candidates:
        key = (candidate["name"].lower(), candidate["url"])
        existing = merged.get(key)
        if not existing:
            merged[key] = candidate
            continue
        existing["score"] = max(existing.get("score", 0.0), candidate.get("score", 0.0))
        if existing.get("source") != candidate.get("source"):
            existing["source"] = "semantic+keyword"

    ranked = sorted(merged.values(), key=lambda item: item.get("score", 0.0), reverse=True)
    return [
        {
            "name": item["name"],
            "url": item["url"],
            "score": round(float(item.get("score", 0.0)), 4),
            "source": item.get("source", ""),
        }
        for item in ranked[:max_results]
    ]


def fallback_topic_summary(topic_name: str, key_points: List[str]) -> str:
    if key_points:
        return "Key points: " + "; ".join(key_points)
    return f"Discussion summary for {topic_name} is pending refinement."


def stringify_collection(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, dict):
        return [f"{k}: {v}" for k, v in values.items()]
    if isinstance(values, list):
        return [str(item) for item in values if item]
    return [str(values)]


def format_action_item_text(item: Any) -> str:
    if isinstance(item, dict):
        parts = [item.get("task")]
        if item.get("responsible_party"):
            parts.append(f"Responsible: {item['responsible_party']}")
        if item.get("timeline"):
            parts.append(f"Timeline: {item['timeline']}")
        if item.get("priority"):
            parts.append(f"Priority: {item['priority']}")
        return " | ".join(part for part in parts if part)
    return str(item)


def format_action_items_for_topic(action_items: Any) -> List[str]:
    if not action_items:
        return []

    formatted_items: List[str] = []
    for item in action_items:
        if item:
            formatted_items.append(format_action_item_text(item))
    return [entry for entry in formatted_items if entry]


def build_session_summary_payload(
    audio_processor,
    final_summary: Dict[str, Any],
    topic_summaries: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    topics: List[str] = []
    for topic in final_summary.get("topics_discussed", []) or []:
        if isinstance(topic, dict):
            topics.append(topic.get("topic") or topic.get("name") or "Topic")
        else:
            topics.append(str(topic))

    action_items = [format_action_item_text(item) for item in final_summary.get("action_items", []) or []]
    structured_topics = topic_summaries or []

    related_services: List[Dict[str, Any]] = []
    for resource in final_summary.get("resources_mentioned", []) or []:
        if isinstance(resource, str):
            related_services.append({"name": resource, "url": ""})
        elif isinstance(resource, dict):
            related_services.append({
                "name": resource.get("name") or resource.get("title") or "Resource",
                "url": resource.get("url", ""),
            })

    for topic in structured_topics:
        if not isinstance(topic, dict):
            continue
        topic_services = topic.get("related_services") or []
        for service in topic_services:
            if not isinstance(service, dict):
                continue
            name = str(service.get("name") or "").strip()
            if not name:
                continue
            url = str(service.get("url") or "").strip()
            exists = any(
                name.lower() == str(existing.get("name", "")).lower()
                and url == str(existing.get("url", ""))
                for existing in related_services
            )
            if not exists:
                related_services.append({"name": name, "url": url})

    topic_names_from_structured = [
        topic.get("topic")
        for topic in structured_topics
        if isinstance(topic, dict) and topic.get("topic")
    ]
    topic_names_from_structured = [name for name in topic_names_from_structured if name]
    topics_for_output = topic_names_from_structured or topics

    return {
        "overview": final_summary.get("executive_summary", "Session summary unavailable."),
        "action_items": action_items,
        "topics_discussed": structured_topics or topics,
        "related_services": related_services,
        "output_for": topics_for_output,
        "confidence_score": 0.9,
        "summary_model": getattr(audio_processor, "summary_model", None),
    }
