# -*- coding: utf-8 -*-
"""
Stage 8 · Extract Tags from Additional Info & Other Feedback
=============================================================
Reads the CRM form parsed JSON (stage 6 output), sends the
"Any Additional Information" and "Any other Feedback" fields to the LLM,
and asks it to produce 5-6 concise category tags for each.

Output: 8_tags.json with structure:
  {
    "additional_info_tags": ["tag1", "tag2", ...],
    "other_feedback_tags": ["tag1", "tag2", ...]
  }

Also patches the CRM form parsed JSON in-place to include these tags.
"""

import json
import sys
from pathlib import Path
from typing import List

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from speech_analysis_qa.speech_pipeline.common.config import (
    HF_TOKEN, QA_MODEL_NAME,
)
from speech_analysis_qa.speech_pipeline.common.llm_utils import load_llm, ask_question
from speech_analysis_qa.speech_pipeline.common.json_utils import extract_json

TAGS_JSON_NAME = "8_tags.json"

SKIP_VALUES = {"Not mentioned in transcript.", "", None}


def _extract_tags(tokenizer, model, text: str, field_name: str) -> List[str]:
    """Ask the LLM to produce 5-6 short keyword tags for the given text."""
    if not text or text.strip() in SKIP_VALUES:
        return []

    prompt = f"""Extract 5-6 very short keyword tags from this CRM note. Each tag must be 1-2 words MAX (like "daycare", "transportation", "language concern", "Kela benefits"). No full sentences.

Text:
\"\"\"{text}\"\"\"

Return ONLY a JSON array of short keyword strings. Example format: ["daycare", "transportation", "dietary needs", "admission process", "language support"]"""

    raw = ask_question(tokenizer, model, prompt, max_new_tokens=200)
    try:
        parsed = extract_json(raw)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if t and str(t).strip()][:6]
    except Exception:
        pass
    # Fallback: try to parse directly
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if t and str(t).strip()][:6]
    except Exception:
        pass
    return []


def run(crm_form_parsed_path: str, output_path: str = None) -> dict:
    """Run stage 8: extract tags from additional info and other feedback."""
    crm_path = Path(crm_form_parsed_path)
    if not crm_path.exists():
        print(f"Stage 8: CRM form not found at {crm_path}, skipping.")
        return {"additional_info_tags": [], "other_feedback_tags": []}

    with open(crm_path, "r", encoding="utf-8") as f:
        crm_data = json.load(f)

    questionnaire = crm_data.get("questionnaire", {})
    form = crm_data.get("form", {})

    # Q20: Additional Info (free text)
    additional_info_text = (
        form.get("additionalInfoText")
        or questionnaire.get("Any Additional Information", "")
    )
    # Q22: Other Feedback (free text)
    other_feedback = (
        form.get("otherFeedback")
        or questionnaire.get("Any other Feedback", "")
    )

    if additional_info_text in SKIP_VALUES and other_feedback in SKIP_VALUES:
        print("Stage 8: Both Q20 and Q22 fields empty, skipping LLM call.")
        result = {"additional_info_text_tags": [], "other_feedback_tags": []}
    else:
        print("Stage 8: Loading LLM for tag extraction...")
        tokenizer, model = load_llm(QA_MODEL_NAME, HF_TOKEN)

        additional_info_text_tags = _extract_tags(
            tokenizer, model, additional_info_text, "Additional Info (Q20)"
        )
        other_feedback_tags = _extract_tags(
            tokenizer, model, other_feedback, "Other Feedback (Q22)"
        )

        result = {
            "additional_info_text_tags": additional_info_text_tags,
            "other_feedback_tags": other_feedback_tags,
        }
        print(f"Stage 8: Extracted tags - Q20 additional_info_text: {additional_info_text_tags}")
        print(f"Stage 8: Extracted tags - Q22 other_feedback: {other_feedback_tags}")

    # Write tags JSON
    if output_path is None:
        output_path = str(crm_path.parent / TAGS_JSON_NAME)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Patch the CRM form JSON to include tags
    crm_data.setdefault("form", {})["additional_info_text_tags"] = result["additional_info_text_tags"]
    crm_data.setdefault("form", {})["other_feedback_tags"] = result["other_feedback_tags"]
    with open(crm_path, "w", encoding="utf-8") as f:
        json.dump(crm_data, f, indent=2, ensure_ascii=False)

    print(f"Stage 8: Tags saved to {output_path}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 8: Extract tags from Additional Info & Other Feedback")
    parser.add_argument("crm_form_parsed_path")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    run(args.crm_form_parsed_path, args.output)
