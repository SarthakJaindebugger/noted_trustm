# -*- coding: utf-8 -*-
"""
Stage 2 · Diarized JSON -> Private Transcript + Mapping
===========================================================
Anonymises the "text" field of every segment (names, Finnish HETU,
passport numbers, phone numbers, and full street addresses shortened to
city/country) and writes out:
  - the private transcript (same shape as stage 1's output, redacted text)
  - mapping.json (placeholder -> original value), consumed by stage 5

Refactored from privacy_json.py. All the anonymisation logic itself now
lives in common/privacy_utils.py so it can be unit tested / reused
without needing to re-copy it here.
"""

import json
from typing import List, Dict, Tuple

from common.privacy_utils import PlaceholderMapper, load_spacy_model


def anonymize_transcript(segments: List[Dict]) -> Tuple[List[Dict], Dict[str, str]]:
    """Returns (private_segments, reverse_mapping)."""
    nlp = load_spacy_model()
    mapper = PlaceholderMapper(nlp)
    private_segments = mapper.anonymize_segments(segments)
    return private_segments, mapper.reverse_mapping


def run(diarized_json_path: str, private_transcript_out: str, mapping_out: str):
    with open(diarized_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    private_segments, reverse_mapping = anonymize_transcript(segments)

    with open(private_transcript_out, "w", encoding="utf-8") as f:
        json.dump(private_segments, f, indent=2, ensure_ascii=False)

    with open(mapping_out, "w", encoding="utf-8") as f:
        json.dump(reverse_mapping, f, indent=2, ensure_ascii=False)

    print(f"Private transcript -> {private_transcript_out}")
    print(f"Mapping            -> {mapping_out}")
    return private_segments, reverse_mapping


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2: diarized JSON -> private transcript + mapping")
    parser.add_argument("diarized_json_path")
    parser.add_argument("private_transcript_out")
    parser.add_argument("mapping_out")
    args = parser.parse_args()
    run(args.diarized_json_path, args.private_transcript_out, args.mapping_out)
