# -*- coding: utf-8 -*-
"""
Stage 3 · Private Transcript -> Metadata JSON
=================================================
Builds the run's metadata: date/time, audio file name, total visit
duration, segment/speaker counts, which raw speaker label (SPEAKER_00,
SPEAKER_01, ...) is the advisor vs. the customer, and -- as requested --
two separate variables holding total advisor speaking time and total
customer speaking time.

The advisor/customer role guess is an LLM call (refactored out of the
"Identify the Advisor(s) and Customer(s)" prompt in pyannote_to_json.py),
run once here rather than being re-asked inside stage 4.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from speech_analysis_qa.speech_pipeline.common.config import ROLE_ID_MODEL_NAME, ROLE_ADVISOR, ROLE_CUSTOMER, HF_TOKEN
from speech_analysis_qa.speech_pipeline.common.text_utils import segments_to_text, format_seconds
from speech_analysis_qa.speech_pipeline.common.json_utils import extract_json
from speech_analysis_qa.speech_pipeline.common.llm_utils import load_llm, ask_question, unload_llm


def compute_speaker_durations(segments: List[Dict]) -> Dict[str, float]:
    """Sum (end - start) per raw speaker label."""
    durations = defaultdict(float)
    for seg in segments:
        durations[seg.get("speaker", "UNKNOWN")] += max(0.0, seg.get("end", 0) - seg.get("start", 0))
    return dict(durations)


def _normalize_role(role: str) -> str:
    if role is None:
        return ""
    normalized = str(role).strip().lower()
    if normalized in {"advisor", "adviser", "advisor (the person giving guidance/help)", "assistant"}:
        return ROLE_ADVISOR
    if normalized in {"customer", "client", "user", "customer (the person seeking help)"}:
        return ROLE_CUSTOMER
    return ""


def _parse_roles_from_text(raw: str, speaker_labels: List[str]) -> Dict[str, str]:
    # Try JSON extraction first.
    try:
        roles = extract_json(raw)
        if isinstance(roles, dict):
            return roles
    except ValueError:
        pass

    # Fallback: regex search for label-role pairs in plain text.
    parsed: Dict[str, str] = {}
    for label in speaker_labels:
        pattern = rf"{label}\s*[:\-]\s*(advisor|customer|adviser|client|user|assistant)"
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            parsed[label] = match.group(1)
            continue

        pattern = rf'"{label}"\s*[:]\s*"?(advisor|customer|adviser|client|user|assistant)"?'
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            parsed[label] = match.group(1)
            continue

    return parsed


def identify_speaker_roles(segments: List[Dict], tokenizer, model) -> Dict[str, str]:
    """Ask the LLM which raw speaker label is the advisor and which is the
    customer. Returns {"SPEAKER_00": "advisor", "SPEAKER_01": "customer", ...}.
    Any speaker the model can't place is left out (treated as neither)."""
    transcript_text = segments_to_text(segments, with_timestamps=True)
    speaker_labels = sorted({seg.get("speaker", "UNKNOWN") for seg in segments})

    prompt = f"""
Based on this transcript, identify the Advisor(s) and Customer(s).

You are an expert conversation analyst. Below is a transcript of a customer
guidance/advice visit, with each line prefixed by a raw speaker label.

-------------------------
{transcript_text}
-------------------------

The speaker labels present are: {", ".join(speaker_labels)}.
There are {len(speaker_labels)} speaker labels in total.

Assign every speaker label to exactly one of the following exact role
values:
- "advisor"
- "customer"

The advisor is the person giving guidance or help. The customer is the
person seeking help or advice.

Every speaker label must be assigned a role. The sum of advisor(s) and
customer(s) must equal the total number of speaker labels.

Return ONLY a valid JSON object mapping each speaker label to one of these
lowercase strings: "advisor" or "customer".
Do not include markdown, explanation, analysis, or any extra text.
Example: {{"SPEAKER_00": "advisor", "SPEAKER_01": "customer"}}
"""
    raw = ask_question(tokenizer, model, prompt, max_new_tokens=256)

    roles = _parse_roles_from_text(raw, speaker_labels)
    if not roles:
        print("WARNING: could not parse speaker-role JSON from LLM output; leaving roles empty.")
        print("LLM raw output:\n", raw)

    normalized_roles: Dict[str, str] = {}
    for label, role in roles.items():
        if label not in speaker_labels:
            continue
        normalized_role = _normalize_role(role)
        if normalized_role:
            normalized_roles[label] = normalized_role

    if len(normalized_roles) != len(speaker_labels):
        print("WARNING: speaker roles did not cover all diarized speakers.")
        print("Expected labels:", speaker_labels)
        print("Parsed roles:", normalized_roles)
        print("LLM raw output:\n", raw)

    return normalized_roles


def build_metadata(segments: List[Dict], audio_file: str, speaker_roles: Dict[str, str]) -> Dict:
    durations = compute_speaker_durations(segments)

    total_advisor_time_sec = sum(
        secs for speaker, secs in durations.items()
        if speaker != "UNKNOWN" and speaker_roles.get(speaker) == ROLE_ADVISOR
    )
    total_customer_time_sec = sum(
        secs for speaker, secs in durations.items()
        if speaker != "UNKNOWN" and speaker_roles.get(speaker) == ROLE_CUSTOMER
    )

    total_duration_sec = max((seg.get("end", 0) for seg in segments), default=0.0)

    return {
        "date_time": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "audio_file": os.path.basename(audio_file),
        "visit_duration": format_seconds(total_duration_sec),
        "audio_duration_sec": round(total_duration_sec, 2),
        "segment_count": len(segments),
        "speakers_detected": sorted({seg.get("speaker", "UNKNOWN") for seg in segments if seg.get("speaker", "UNKNOWN") != "UNKNOWN"}),
        "speaker_roles": speaker_roles,
        "speaker_durations_sec": {k: round(v, 2) for k, v in durations.items() if k != "UNKNOWN"},
        # The two variables requested: total advisor time vs. total user/customer time.
        "total_advisor_time_sec": round(total_advisor_time_sec, 2),
        "total_advisor_time": format_seconds(total_advisor_time_sec),
        "total_customer_time_sec": round(total_customer_time_sec, 2),
        "total_customer_time": format_seconds(total_customer_time_sec),
    }


def run(private_transcript_path: str, audio_file: str, output_path: str) -> Tuple[Dict, float, float]:
    with open(private_transcript_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    tokenizer, model = load_llm(ROLE_ID_MODEL_NAME, HF_TOKEN)
    try:
        speaker_roles = identify_speaker_roles(segments, tokenizer, model)
    finally:
        unload_llm(ROLE_ID_MODEL_NAME, HF_TOKEN)

    metadata = build_metadata(segments, audio_file, speaker_roles)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Metadata -> {output_path}")

    # The two separate variables the caller asked for.
    total_advisor_time_sec = metadata["total_advisor_time_sec"]
    total_customer_time_sec = metadata["total_customer_time_sec"]
    return metadata, total_advisor_time_sec, total_customer_time_sec


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 3: private transcript -> metadata JSON")
    parser.add_argument("private_transcript_path")
    parser.add_argument("audio_file")
    parser.add_argument("output_path")
    args = parser.parse_args()
    run(args.private_transcript_path, args.audio_file, args.output_path)
