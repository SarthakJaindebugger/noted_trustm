#!/usr/bin/env python3
"""
Download the AxonData/multilingual-call-center-speech-dataset from Hugging Face Hub
to a specified local directory.
"""

import os
import sys
from pathlib import Path

# ========================== CONFIGURATION ==========================
DATASET_ID = "AxonData/multilingual-call-center-speech-dataset"
LOCAL_DIR = Path("/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/AxonSpeechData")

# ========================== SETUP ==========================
def setup_directories():
    """Ensure the local directory exists."""
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Local directory ready: {LOCAL_DIR}")

def check_hf_token():
    """Check if huggingface_hub is installed and optionally check token."""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        # Optional: Check if user is logged in (do not fail if not)
        try:
            user = api.whoami()
            print(f"✅ Logged in as: {user.get('name', 'unknown')}")
        except Exception:
            print("⚠️  Not logged in to Hugging Face. Some gated datasets may not be accessible.")
    except ImportError:
        print("❌ huggingface_hub not installed. Install it with: pip install huggingface_hub")
        sys.exit(1)

# ========================== METHOD 1: Using huggingface_hub CLI ==========================
def download_with_cli():
    """
    Use the huggingface-cli command to download the dataset.
    This method preserves the exact repository structure (including .docx and .mp3 files).
    """
    import subprocess
    import shutil

    # Check if huggingface-cli is available
    if not shutil.which("huggingface-cli"):
        print("❌ 'huggingface-cli' not found. Install it with: pip install huggingface_hub")
        return False

    print("🚀 Downloading dataset using huggingface-cli...")
    cmd = [
        "huggingface-cli", "download",
        DATASET_ID,
        "--repo-type", "dataset",
        "--local-dir", str(LOCAL_DIR),
        "--local-dir-use-symlinks", "False"   # Copy files directly (no symlinks)
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Dataset successfully downloaded to: {LOCAL_DIR}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ CLI download failed: {e}")
        return False

# ========================== METHOD 2: Using huggingface_hub Python API ==========================
def download_with_api():
    """
    Use the huggingface_hub Python API to download all files individually.
    This method gives more control and works well in automated scripts.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("❌ huggingface_hub not installed. Install it with: pip install huggingface_hub")
        return False

    print("🚀 Downloading dataset using snapshot_download()...")
    try:
        snapshot_download(
            repo_id=DATASET_ID,
            repo_type="dataset",
            local_dir=str(LOCAL_DIR),
            local_dir_use_symlinks=False,
            resume_download=True,
            max_workers=4
        )
        print(f"✅ Dataset successfully downloaded to: {LOCAL_DIR}")
        return True
    except Exception as e:
        print(f"❌ API download failed: {e}")
        return False

# ========================== METHOD 3: Using datasets library (optional) ==========================
def download_with_datasets():
    """
    Use the datasets library to load and optionally save the dataset.
    Note: This method may not download the raw audio files in their original folder structure.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("❌ datasets library not installed. Install it with: pip install datasets")
        return False

    print("🚀 Loading dataset with load_dataset()...")
    try:
        # Load the dataset (this automatically downloads and caches it)
        dataset = load_dataset(DATASET_ID, trust_remote_code=True)
        print("✅ Dataset loaded successfully!")
        print(f"📊 Dataset splits: {list(dataset.keys())}")
        # Optionally, save the dataset to the local directory in Arrow format
        dataset.save_to_disk(LOCAL_DIR / "dataset_cache")
        print(f"💾 Dataset cached to: {LOCAL_DIR / 'dataset_cache'}")
        return True
    except Exception as e:
        print(f"❌ datasets load failed: {e}")
        return False

# ========================== MAIN ==========================
def main():
    print(f"📀 Hugging Face Dataset: {DATASET_ID}")
    print(f"📁 Target Directory: {LOCAL_DIR}")

    setup_directories()
    check_hf_token()

    # Try method 1 (CLI) - recommended for full folder structure
    if download_with_cli():
        return

    # Fallback to method 2 (API)
    print("\n🔄 Falling back to API method...")
    if download_with_api():
        return

    # Final fallback to datasets library
    print("\n🔄 Falling back to datasets library...")
    download_with_datasets()

if __name__ == "__main__":
    main()