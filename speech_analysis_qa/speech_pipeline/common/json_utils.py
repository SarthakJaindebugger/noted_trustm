# -*- coding: utf-8 -*-
"""
common/json_utils.py
=====================
Parsing helpers for turning noisy LLM text output into clean JSON /
strings. Both the role-identification step (stage 3) and the structured
Q&A step (stage 4) need to strip <think> tags, markdown fences, etc. --
this used to be duplicated between privacy_rag_2_outputs.py and
audio_to_csv_json.py's parse_json_from_llm. Now there is one version.
"""

import json
import re


def clean_answer(text: str) -> str:
    """Strip <think> reasoning blocks and code fences from a raw LLM reply."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    text = text.replace("```json", "").replace("```", "").strip()
    if not text:
        text = "Not mentioned in transcript."
    return text


def extract_json(text: str) -> dict:
    """Pull the first {...} JSON object out of a raw LLM reply, tolerating
    markdown fences and surrounding prose."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end + 1]
        else:
            raise ValueError("No JSON object found in LLM output")

    return json.loads(json_str)
