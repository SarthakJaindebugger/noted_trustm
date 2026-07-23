# -*- coding: utf-8 -*-
"""
run_pipeline.py
=================
Runs the full pipeline end-to-end, in order:

  1) Input Raw Audio
        -> stage1_diarize_transcribe.run()
  2) The pyannote JSON (diarized + transcribed segments)
        -> feeds stage 2
  3) Privacy JSON + mapping
        -> stage2_privacy.run()
  4) Metadata JSON (incl. total_advisor_time_sec / total_customer_time_sec)
        -> stage3_metadata.run()
  5) Questions & Answers JSON (private, placeholders intact)
        -> stage4_qa_private.run()
  6) Mapped JSON (final, de-anonymized)
        -> stage5_apply_mapping.run()

Every stage reads/writes plain JSON files on disk, so you can also run
any stage_*.py on its own (see each file's `if __name__ == "__main__"`
block) and re-enter the pipeline at any point.
"""

import os
import argparse

from common.config import (
    DIARIZED_JSON_NAME, PRIVATE_TRANSCRIPT_JSON_NAME, MAPPING_JSON_NAME,
    METADATA_JSON_NAME, PRIVATE_RESULTS_JSON_NAME, MAPPED_RESULTS_JSON_NAME,
)
import stage1_diarize_transcribe
import stage2_privacy
import stage3_metadata
import stage4_qa_private
import stage5_apply_mapping


def run_pipeline(audio_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    diarized_json_path = os.path.join(output_dir, DIARIZED_JSON_NAME)
    private_transcript_path = os.path.join(output_dir, PRIVATE_TRANSCRIPT_JSON_NAME)
    mapping_path = os.path.join(output_dir, MAPPING_JSON_NAME)
    metadata_path = os.path.join(output_dir, METADATA_JSON_NAME)
    private_results_path = os.path.join(output_dir, PRIVATE_RESULTS_JSON_NAME)
    mapped_results_path = os.path.join(output_dir, MAPPED_RESULTS_JSON_NAME)

    # 1-2) Raw audio -> pyannote (diarized) JSON
    print("\n=== STAGE 1-2: audio -> diarized JSON ===")
    stage1_diarize_transcribe.run(audio_path, diarized_json_path)

    # 3) Privacy JSON + mapping
    print("\n=== STAGE 3: diarized JSON -> private transcript + mapping ===")
    stage2_privacy.run(diarized_json_path, private_transcript_path, mapping_path)

    # 4) Metadata JSON (total_advisor_time_sec / total_customer_time_sec)
    print("\n=== STAGE 4: private transcript -> metadata JSON ===")
    metadata, total_advisor_time_sec, total_customer_time_sec = stage3_metadata.run(
        private_transcript_path, audio_path, metadata_path
    )
    print(f"Total advisor time (sec):  {total_advisor_time_sec}")
    print(f"Total customer time (sec): {total_customer_time_sec}")

    # 5) Questions & answers JSON (private)
    print("\n=== STAGE 5: private transcript -> private Q&A JSON ===")
    stage4_qa_private.run(private_transcript_path, private_results_path)

    # 6) Mapped (de-anonymized) JSON
    print("\n=== STAGE 6: private Q&A JSON + mapping -> mapped JSON ===")
    stage5_apply_mapping.run(private_results_path, mapping_path, mapped_results_path)

    print("\nAll done. Outputs written to:", output_dir)
    return {
        "diarized_json_path": diarized_json_path,
        "private_transcript_path": private_transcript_path,
        "mapping_path": mapping_path,
        "metadata_path": metadata_path,
        "private_results_path": private_results_path,
        "mapped_results_path": mapped_results_path,
        "total_advisor_time_sec": total_advisor_time_sec,
        "total_customer_time_sec": total_customer_time_sec,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full audio -> mapped JSON pipeline")
    parser.add_argument("audio_path", help="Path to the raw input audio file")
    parser.add_argument("output_dir", help="Folder to write all intermediate + final JSON files into")
    args = parser.parse_args()
    run_pipeline(args.audio_path, args.output_dir)
