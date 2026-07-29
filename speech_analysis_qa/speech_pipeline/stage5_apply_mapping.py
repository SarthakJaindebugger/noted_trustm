# -*- coding: utf-8 -*-
"""
Stage 5 · Private Q&A JSON + Mapping -> Mapped (De-anonymized) JSON
========================================================================
Replaces every <PERSON_1> / <FINNISH_HETU_1> / <PASSPORT_1> / <PHONE_1>
style placeholder in stage 4's output with its original value from
stage 2's mapping.json, producing the final, complete result.

Refactored from the tail end of privacy_rag_2_outputs.py.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Set, Union

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def apply_mapping(value: Union[str, Dict, list], mapping: Dict[str, str]):
    """Recursively replace every placeholder occurrence with its mapped value."""
    if isinstance(value, str):
        result = value
        for placeholder in sorted(mapping.keys(), key=len, reverse=True):
            if placeholder in result:
                result = result.replace(placeholder, mapping[placeholder])
        return result
    if isinstance(value, dict):
        return {k: apply_mapping(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [apply_mapping(v, mapping) for v in value]
    return value


def find_placeholders(value, found: Set[str] = None) -> Set[str]:
    """Recursively collect every <SOMETHING_n>-style placeholder actually
    present, so we can flag any that mapping.json doesn't cover."""
    if found is None:
        found = set()
    if isinstance(value, str):
        found.update(re.findall(r"<[A-Z][A-Z_]*_\d+>", value))
    elif isinstance(value, dict):
        for v in value.values():
            find_placeholders(v, found)
    elif isinstance(value, list):
        for v in value:
            find_placeholders(v, found)
    return found


def run(private_results_path: str, mapping_path: str, output_path: str) -> Dict:
    with open(private_results_path, "r", encoding="utf-8") as f:
        private_output = json.load(f)
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    placeholders_used = find_placeholders(private_output)
    missing = sorted(placeholders_used - set(mapping.keys()))
    if missing:
        print(
            f"WARNING: {len(missing)} placeholder(s) appear in the output but have "
            f"NO entry in the mapping, so they will remain UNRESOLVED: {', '.join(missing)}"
        )

    mapped_output = apply_mapping(private_output, mapping)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapped_output, f, indent=2, ensure_ascii=False)
    print(f"Mapped (complete) JSON -> {output_path}")
    return mapped_output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 5: private results + mapping -> mapped JSON")
    parser.add_argument("private_results_path")
    parser.add_argument("mapping_path")
    parser.add_argument("output_path")
    args = parser.parse_args()
    run(args.private_results_path, args.mapping_path, args.output_path)
