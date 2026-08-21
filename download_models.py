#!/usr/bin/env python3
"""Pre-download LLM and embedding models to models/ directory."""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "speech_analysis_qa" / "speech_pipeline"))

from speech_analysis_qa.speech_pipeline.common.config import QA_MODEL_NAME, EMBED_MODEL_NAME
from huggingface_hub import snapshot_download

MODELS_DIR = Path(os.getenv("MODELS_DIR", str(REPO_ROOT / "models")))
HF_TOKEN = os.getenv("HF_TOKEN", "")

models = {
    QA_MODEL_NAME: MODELS_DIR / QA_MODEL_NAME.replace("/", "--"),
    EMBED_MODEL_NAME: MODELS_DIR / EMBED_MODEL_NAME.replace("/", "--"),
}

for name, local_path in models.items():
    if local_path.exists() and any(local_path.iterdir()):
        print(f"[OK] {name} already at {local_path}")
        continue
    print(f"[DOWNLOADING] {name} -> {local_path} ...")
    local_path.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=name, local_dir=str(local_path), token=HF_TOKEN or None)
    print(f"[DONE] {name}")

print("\nAll models ready in:", MODELS_DIR)
