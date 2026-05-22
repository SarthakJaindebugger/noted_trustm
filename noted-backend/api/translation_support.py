import json
import re
from typing import Any, List, Optional, Tuple


NON_TRANSLATABLE_KEYS = {"url", "link", "service_link"}


def build_summary_text(stored_summary) -> str:
    """Build a readable text block from the stored summary for translation."""
    parts = []
    if stored_summary.overview:
        parts.append(f"Executive Summary:\n{stored_summary.overview}")

    if stored_summary.topics_discussed:
        topics_text = []
        for topic in stored_summary.topics_discussed:
            if isinstance(topic, str):
                topics_text.append(f"- {topic}")
            elif isinstance(topic, dict):
                name = topic.get("topic", "Topic")
                summary = topic.get("summary", topic.get("content", ""))
                topics_text.append(f"- {name}: {summary}")
        if topics_text:
            parts.append("Topics Discussed:\n" + "\n".join(topics_text))

    if stored_summary.action_items:
        items = []
        for item in stored_summary.action_items:
            if isinstance(item, str):
                items.append(f"- {item}")
            elif isinstance(item, dict):
                task = item.get("task", str(item))
                items.append(f"- {task}")
        if items:
            parts.append("Action Items:\n" + "\n".join(items))

    return "\n\n".join(parts)


def looks_like_link(text: str) -> bool:
    value = (text or "").strip().lower()
    if not value:
        return False
    return (
        value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("www.")
        or value.startswith("mailto:")
        or value.startswith("tel:")
        or "://" in value
    )


def collect_translatable_strings(
    value: Any,
    path: Tuple[Any, ...] = (),
    parent_key: Optional[str] = None,
) -> List[Tuple[Tuple[Any, ...], str]]:
    entries: List[Tuple[Tuple[Any, ...], str]] = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            entries.extend(collect_translatable_strings(nested_value, path + (key,), key))
        return entries

    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            entries.extend(collect_translatable_strings(nested_value, path + (index,), parent_key))
        return entries

    if isinstance(value, str):
        if not value.strip():
            return entries
        if parent_key in NON_TRANSLATABLE_KEYS:
            return entries
        if looks_like_link(value):
            return entries
        entries.append((path, value))

    return entries


def set_value_at_path(root: Any, path: Tuple[Any, ...], new_value: str) -> None:
    target = root
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = new_value


def parse_translation_list(content: str, expected_count: int) -> List[str]:
    payload = None
    cleaned = (content or "").strip()
    if not cleaned:
        raise ValueError("Translation model returned empty content")

    try:
        payload = json.loads(cleaned)
    except Exception:
        array_match = re.search(r"\[[\s\S]*\]", cleaned)
        if array_match:
            payload = json.loads(array_match.group(0))
        else:
            object_match = re.search(r"\{[\s\S]*\}", cleaned)
            if object_match:
                payload = json.loads(object_match.group(0))

    if isinstance(payload, dict):
        payload = payload.get("translations")

    if not isinstance(payload, list):
        raise ValueError("Translation model did not return a JSON list")

    if len(payload) != expected_count:
        raise ValueError(
            f"Expected {expected_count} translated strings, got {len(payload)}"
        )

    return [str(item) if item is not None else "" for item in payload]


def translate_string_batch(audio_processor, texts: List[str], target_language: str) -> List[str]:
    if not texts:
        return []

    client = audio_processor.openai_client
    model = audio_processor.summary_model

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a professional translator. Translate each array element into {target_language}. "
                    "Return ONLY valid JSON array of translated strings in the same order and same length. "
                    "Do not add or remove items."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(texts, ensure_ascii=False),
            },
        ],
        temperature=0.0,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    from utils.text import strip_think_tags

    content = strip_think_tags(response.choices[0].message.content or "")
    return parse_translation_list(content, len(texts))


def translate_text(audio_processor, summary_text: str, target_language: str, stored_summary) -> dict:
    """Translate session summary fields while preserving the original JSON structure."""
    source_summary = {
        "overview": stored_summary.overview or "",
        "topics_discussed": stored_summary.topics_discussed or [],
        "action_items": stored_summary.action_items or [],
        "related_services": stored_summary.related_services or [],
    }

    try:
        translated_summary = json.loads(json.dumps(source_summary, ensure_ascii=False))
        entries = collect_translatable_strings(translated_summary)
        texts_to_translate = [text for _, text in entries]

        if texts_to_translate:
            translated_texts = translate_string_batch(
                audio_processor, texts_to_translate, target_language
            )
            for (path, _), translated_text in zip(entries, translated_texts):
                set_value_at_path(translated_summary, path, translated_text)

        translated_summary["executive_summary"] = translated_summary.get("overview", "")
        return translated_summary
    except Exception:
        fallback = json.loads(json.dumps(source_summary, ensure_ascii=False))
        if summary_text.strip():
            translated_overview = translate_string_batch(
                audio_processor, [summary_text], target_language
            )[0]
            fallback["overview"] = translated_overview
            fallback["executive_summary"] = translated_overview
        else:
            fallback["executive_summary"] = fallback.get("overview", "")
        return fallback
