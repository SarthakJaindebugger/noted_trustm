# -*- coding: utf-8 -*-
"""
run_pipeline.py
=================
Runs the full speech-analysis pipeline for one audio file or for every
user recording under the repository knowledgebase layout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from speech_analysis_qa.speech_pipeline.common.config import (  # noqa: E402
    CRM_FORM_PARSED_HTML_NAME,
    CRM_FORM_PARSED_JSON_NAME,
    DIARIZED_JSON_NAME,
    MAPPED_RESULTS_JSON_NAME,
    MAPPING_JSON_NAME,
    METADATA_JSON_NAME,
    PRIVATE_RESULTS_JSON_NAME,
    PRIVATE_TRANSCRIPT_JSON_NAME,
)
from speech_analysis_qa.utils import sanitize_username, write_json  # noqa: E402

DEFAULT_USERS_ROOT = REPO_ROOT / "knowledgebase" / "users_admin_data" / "users"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


def _audio_stem(audio_path: str | Path) -> str:
    return Path(audio_path).stem


def user_dirs(users_root: str | Path, username: str) -> Dict[str, Path]:
    user_root = Path(users_root) / sanitize_username(username)
    dirs = {
        "root": user_root,
        "recordings": user_root / "recordings",
        "uploads": user_root / "uploads",
        "embedding": user_root / "embedding",
    }
    # Also create the plural spelling for compatibility with existing callers.
    dirs["embeddings"] = user_root / "embeddings"
    dirs["uploads"].mkdir(parents=True, exist_ok=True)
    dirs["embedding"].mkdir(parents=True, exist_ok=True)
    dirs["embeddings"].mkdir(parents=True, exist_ok=True)
    return dirs


def output_paths_for_audio(audio_path: str | Path, uploads_dir: str | Path) -> Dict[str, str]:
    stem = _audio_stem(audio_path)
    run_dir = Path(uploads_dir) / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "output_dir": str(run_dir),
        "diarized_json_path": str(run_dir / DIARIZED_JSON_NAME),
        "private_transcript_path": str(run_dir / PRIVATE_TRANSCRIPT_JSON_NAME),
        "mapping_path": str(run_dir / MAPPING_JSON_NAME),
        "metadata_path": str(run_dir / METADATA_JSON_NAME),
        "private_results_path": str(run_dir / PRIVATE_RESULTS_JSON_NAME),
        "mapped_results_path": str(run_dir / MAPPED_RESULTS_JSON_NAME),
        "crm_form_parsed_path": str(run_dir / CRM_FORM_PARSED_JSON_NAME),
        "crm_form_html_path": str(run_dir / CRM_FORM_PARSED_HTML_NAME),
    }


def write_embedding_chunks(
    private_transcript_path: str | Path,
    audio_path: str | Path,
    embedding_dir: str | Path,
    username: Optional[str] = None,
    upsert_qdrant: bool = True,
) -> List[str]:
    """Chunk, embed, persist per-chunk JSON, and optionally upsert to Qdrant."""
    stem = _audio_stem(audio_path)
    embedding_dir = Path(embedding_dir)
    embedding_dir.mkdir(parents=True, exist_ok=True)

    from speech_analysis_qa.rag import RagPipeline
    from speech_analysis_qa.transcript_chunking import chunk_transcript_file

    chunks = chunk_transcript_file(private_transcript_path)
    if not chunks:
        return []

    rag = RagPipeline()
    vectors = rag.embedder.embed_texts([chunk["text"] for chunk in chunks])
    metadata = {"username": username, "audio_file": Path(audio_path).name, "audio_stem": stem}

    enriched = []
    written_paths = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors), start=1):
        chunk_record = dict(chunk)
        chunk_record["chunk_id"] = f"{stem}_chunk{index}"
        chunk_record["embedding"] = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        chunk_record["metadata"] = metadata
        file_path = embedding_dir / f"{stem}_chunk{index}_embedding.json"
        write_json(chunk_record, file_path)
        written_paths.append(str(file_path))
        enriched.append(chunk_record)

    if upsert_qdrant:
        rag.store.create_collection(vector_size=len(enriched[0]["embedding"]))
        rag.upsert_chunks(enriched, metadata)

    manifest = {
        "audio_file": Path(audio_path).name,
        "private_transcript_path": str(private_transcript_path),
        "chunk_count": len(enriched),
        "chunk_files": written_paths,
    }
    write_json(manifest, embedding_dir / f"{stem}_embedding_manifest.json")
    return written_paths


def run_pipeline(
    audio_path: str,
    output_dir: str,
    embedding_dir: Optional[str] = None,
    username: Optional[str] = None,
    cleanup_stage1: bool = True,
    cleanup_llm: bool = True,
):
    # Ensure HF token (if provided via env or CLI) is available to downstream
    # stages that import model utilities at import time. Import stage modules
    # here so they pick up any HF token set on the environment before use.
    import os as _os

    # We'll import stage modules only when their outputs are required so
    # expensive model loading inside a stage.run() is avoided when the
    # stage's output file is already present. Use importlib below.
    import importlib as _importlib
    _import_stage = lambda name: _importlib.import_module(f"speech_analysis_qa.speech_pipeline.{name}")
    if embedding_dir:
        paths = output_paths_for_audio(audio_path, output_dir)
    else:
        run_dir = Path(output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "output_dir": str(run_dir),
            "diarized_json_path": str(run_dir / DIARIZED_JSON_NAME),
            "private_transcript_path": str(run_dir / PRIVATE_TRANSCRIPT_JSON_NAME),
            "mapping_path": str(run_dir / MAPPING_JSON_NAME),
            "metadata_path": str(run_dir / METADATA_JSON_NAME),
            "private_results_path": str(run_dir / PRIVATE_RESULTS_JSON_NAME),
            "mapped_results_path": str(run_dir / MAPPED_RESULTS_JSON_NAME),
            "crm_form_parsed_path": str(run_dir / CRM_FORM_PARSED_JSON_NAME),
            "crm_form_html_path": str(run_dir / CRM_FORM_PARSED_HTML_NAME),
        }

    try:
        print("\n=== STAGE 1: audio -> diarized transcript ===")
        if Path(paths["diarized_json_path"]).exists():
            print(f"Skipping stage1: {paths['diarized_json_path']} already exists")
        else:
            stage1 = _import_stage("stage1_diarize_transcribe")
            stage1.run(audio_path, paths["diarized_json_path"])

        print("\n=== STAGE 2: diarized transcript -> private transcript + mapping ===")
        if Path(paths["private_transcript_path"]).exists() and Path(paths["mapping_path"]).exists():
            print(f"Skipping stage2: {paths['private_transcript_path']} and {paths['mapping_path']} already exist")
        else:
            stage2 = _import_stage("stage2_privacy")
            stage2.run(paths["diarized_json_path"], paths["private_transcript_path"], paths["mapping_path"])

        print("\n=== STAGE 3: private transcript -> metadata JSON ===")
        if Path(paths["metadata_path"]).exists():
            print(f"Skipping stage3: {paths['metadata_path']} already exists")
            total_advisor_time_sec = 0.0
            total_customer_time_sec = 0.0
        else:
            stage3 = _import_stage("stage3_metadata")
            _, total_advisor_time_sec, total_customer_time_sec = stage3.run(
                paths["private_transcript_path"], audio_path, paths["metadata_path"]
            )

        # Stage 4: private transcript -> private Q&A JSON
        print("\n=== STAGE 4: private transcript -> private Q&A JSON ===")
        if Path(paths["private_results_path"]).exists():
            print(f"Skipping stage4: {paths['private_results_path']} already exists")
        else:
            stage4 = _import_stage("stage4_qa_private")
            stage4.run(paths["private_transcript_path"], paths["private_results_path"])

        # Stage 5: private Q&A JSON + mapping -> mapped JSON
        print("\n=== STAGE 5: private Q&A JSON + mapping -> mapped JSON ===")
        if Path(paths["mapped_results_path"]).exists():
            print(f"Skipping stage5: {paths['mapped_results_path']} already exists")
        else:
            stage5 = _import_stage("stage5_apply_mapping")
            stage5.run(paths["private_results_path"], paths["mapping_path"], paths["mapped_results_path"])

        # Stage 6: mapped JSON -> CRM form parsed JSON
        print("\n=== STAGE 6: mapped JSON -> CRM form parsed JSON ===")
        if Path(paths["crm_form_parsed_path"]).exists() and Path(paths["crm_form_html_path"]).exists():
            print(f"Skipping stage6: {paths['crm_form_parsed_path']} and {paths['crm_form_html_path']} already exist")
        else:
            stage6 = _import_stage("stage6_crm_form_parsing")
            stage6.run(
                paths["mapped_results_path"],
                paths["metadata_path"],
                paths["crm_form_parsed_path"],
                paths["crm_form_html_path"],
            )

        embedding_paths: List[str] = []
        if embedding_dir:
            if Path(embedding_dir).exists() and any(Path(embedding_dir).glob("*_embedding_manifest.json")):
                print(f"Skipping embeddings: embedding manifest exists under {embedding_dir}")
            else:
                print("\n=== STAGE 7: private transcript -> chunk embeddings ===")
                embedding_paths = write_embedding_chunks(
                    paths["private_transcript_path"], audio_path, embedding_dir, username=username
                )

        print("All done. Outputs written to:", paths["output_dir"])
        return {
            **paths,
            "embedding_paths": embedding_paths,
            "total_advisor_time_sec": total_advisor_time_sec,
            "total_customer_time_sec": total_customer_time_sec,
        }
    finally:
        if cleanup_llm:
            try:
                from speech_analysis_qa.speech_pipeline.common.llm_utils import unload_all_llms

                unload_all_llms()
            except Exception:
                pass


def iter_user_audio(users_root: str | Path, username: Optional[str] = None) -> Iterable[tuple[str, Path]]:
    roots = (
        [Path(users_root) / sanitize_username(username)]
        if username
        else sorted(p for p in Path(users_root).iterdir() if p.is_dir())
    )
    for user_root in roots:
        recordings = user_root / "recordings"
        if not recordings.exists():
            continue
        for audio in sorted(
            p for p in recordings.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ):
            yield user_root.name, audio


def run_users(users_root: str | Path = DEFAULT_USERS_ROOT, username: Optional[str] = None) -> List[Dict]:
    results = []
    stage1_module = None
    try:
        for user, audio_path in iter_user_audio(users_root, username):
            dirs = user_dirs(users_root, user)
            print(f"\n### Processing user={user} audio={audio_path.name} ###")
            results.append(run_pipeline(
                str(audio_path),
                str(dirs["uploads"]),
                str(dirs["embedding"]),
                username=user,
                cleanup_stage1=True,
                cleanup_llm=True,
            ))
        return results
    finally:
        try:
            from speech_analysis_qa.speech_pipeline import stage1_diarize_transcribe
            stage1_diarize_transcribe.cleanup()
        except Exception:
            pass
        try:
            from speech_analysis_qa.speech_pipeline.common.llm_utils import unload_all_llms
            unload_all_llms()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run speech analysis for one audio file or user recording folders")
    parser.add_argument("audio_path", nargs="?", help="Path to one raw input audio file")
    parser.add_argument("output_dir", nargs="?", help="Folder to write JSON outputs for one audio file")
    parser.add_argument("--users-root", default=str(DEFAULT_USERS_ROOT), help="Root containing per-user folders")
    parser.add_argument("--user", help="Process only this user under --users-root")
    parser.add_argument("--all-users", action="store_true", help="Process recordings for all users under --users-root")
    parser.add_argument("--hf-token", help="Hugging Face token to use for model access (overrides HF_TOKEN env)")
    args = parser.parse_args()

    # If an HF token was provided on the CLI, inject it into the environment
    # before any stage modules are imported so they can pick it up at import time.
    if args.hf_token:
        import os

        os.environ["HF_TOKEN"] = args.hf_token

    if args.all_users or args.user:
        run_users(args.users_root, args.user)
    elif args.audio_path and args.output_dir:
        run_pipeline(args.audio_path, args.output_dir)
    else:
        parser.error("provide audio_path output_dir, or use --all-users/--user")
