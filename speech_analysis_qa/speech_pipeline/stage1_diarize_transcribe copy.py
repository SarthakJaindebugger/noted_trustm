# -*- coding: utf-8 -*-

"""
Stage 1 · Input Raw Audio -> Diarized/Transcribed JSON
=========================================================
Runs pyannote speaker diarization + Whisper ASR.
"""

# ============================================================
# Hugging Face authentication + PyTorch serialization patch
# ============================================================

import os
import functools
import torch


# ---- Hugging Face token ----
# Priority:
# 1. HF_TOKEN environment variable
# 2. HUGGINGFACEHUB_API_TOKEN
# 3. HuggingFace cached login

HF_TOKEN = (
    os.getenv("HF_TOKEN")
    or os.getenv("HUGGINGFACEHUB_API_TOKEN")
)


try:
    from huggingface_hub import login, HfFolder

    if not HF_TOKEN:
        HF_TOKEN = HfFolder.get_token()

    if HF_TOKEN:
        login(
            token=HF_TOKEN,
            add_to_git_credential=False
        )
        print("Hugging Face authentication successful")
    else:
        print(
            "WARNING: No Hugging Face token found. "
            "Set HF_TOKEN environment variable."
        )

except Exception as e:
    print(f"WARNING: HuggingFace login failed: {e}")


# ---- PyTorch 2.6+ checkpoint compatibility ----

try:
    import torch.serialization

    torch.serialization.add_safe_globals(
        [
            torch.torch_version.TorchVersion
        ]
    )

except Exception as e:
    print(
        f"WARNING: Could not add TorchVersion safe global: {e}"
    )


_original_torch_load = torch.load
_original_serialization_load = torch.serialization.load


@functools.wraps(_original_torch_load)
def _patched_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_torch_load(*args, **kwargs)


@functools.wraps(_original_serialization_load)
def _patched_serialization_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_serialization_load(*args, **kwargs)


torch.load = _patched_torch_load
torch.serialization.load = _patched_serialization_load


# ============================================================
# Imports
# ============================================================

import json
import sys
from pathlib import Path
from typing import List, Dict


PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from speech_analysis_qa.speech_pipeline.common.config import (
    DIARIZATION_MODEL,
    WHISPER_MODEL_SIZE,
    TARGET_SAMPLE_RATE,
)

from speech_analysis_qa.speech_pipeline.common.device_utils import (
    get_compute_device,
)


_DIARIZATION_PIPELINE = None
_WHISPER_MODEL_CACHE = {}







def _get_diarization_pipeline(token: str = None):

    global _DIARIZATION_PIPELINE

    if _DIARIZATION_PIPELINE is None:

        from pyannote.audio import Pipeline
        import traceback

        if not token:
            token = HF_TOKEN

        if not token:
            print(
                "WARNING: No HF token found. "
                "pyannote may fail if model is gated."
            )

        try:
            print(
                "Loading pyannote diarization pipeline..."
            )

            _DIARIZATION_PIPELINE = Pipeline.from_pretrained(
                DIARIZATION_MODEL
            )

            print(
                "Pyannote diarization pipeline loaded successfully"
            )

        except Exception as exc:

            traceback.print_exc()

            raise RuntimeError(
                "Failed to load pyannote diarization pipeline.\n"
                f"Original error: {exc}"
            ) from exc


    return _DIARIZATION_PIPELINE



def _get_whisper_model(model_size: str = WHISPER_MODEL_SIZE):
    global _WHISPER_MODEL_CACHE
    if model_size not in _WHISPER_MODEL_CACHE:
        import torch
        from faster_whisper import WhisperModel

        device = get_compute_device(os.getenv("LIGHT_ASR_DEVICE", "auto"))
        compute_type = "int8"

        _WHISPER_MODEL_CACHE[model_size] = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
    return _WHISPER_MODEL_CACHE[model_size]


def cleanup():
    global _DIARIZATION_PIPELINE, _WHISPER_MODEL_CACHE

    _DIARIZATION_PIPELINE = None
    _WHISPER_MODEL_CACHE.clear()

    import gc
    from speech_analysis_qa.speech_pipeline.common.device_utils import clear_torch_cache

    gc.collect()
    clear_torch_cache()


def load_audio(file_path: str, target_sr: int = TARGET_SAMPLE_RATE):
    import librosa
    audio, sr = librosa.load(file_path, sr=target_sr, mono=True)
    return audio, sr


def run_diarization(audio, sr: int, token: str):
    import torch
    pipeline = _get_diarization_pipeline(token)
    waveform = torch.from_numpy(audio).float().unsqueeze(0)
    return pipeline({"waveform": waveform, "sample_rate": sr})


def _normalize_asr_segments(raw_segments) -> List[Dict]:
    normalized = []
    for segment in raw_segments or []:
        if isinstance(segment, dict):
            normalized.append(segment)
            continue

        attrs = getattr(segment, "__dict__", {})
        normalized.append({
            "start": getattr(segment, "start", attrs.get("start", 0)),
            "end": getattr(segment, "end", attrs.get("end", 0)),
            "text": getattr(segment, "text", attrs.get("text", "")),
        })
    return normalized


def run_asr(audio_path: str, model_size: str = WHISPER_MODEL_SIZE) -> List[Dict]:
    model = _get_whisper_model(model_size)
    result = model.transcribe(audio_path, word_timestamps=True)

    if isinstance(result, tuple):
        segments = result[0]
    elif isinstance(result, dict):
        segments = result.get("segments", [])
    else:
        segments = result

    return _normalize_asr_segments(segments)


def assign_speakers_to_asr(diarization, asr_segments):
    # pyannote >=3.3 returns Annotation directly
    if hasattr(diarization, "speaker_diarization"):
        annotation = diarization.speaker_diarization
    else:
        annotation = diarization

    speaker_segments = [
        {
            "start": segment.start,
            "end": segment.end,
            "speaker": speaker,
        }
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]

    speaker_segments.sort(key=lambda x: x["start"])
    asr_segments = sorted(asr_segments, key=lambda x: x["start"])

    output = []

    for asr in asr_segments:
        best_overlap = 0
        best_speaker = "UNKNOWN"

        for sp in speaker_segments:
            overlap = max(
                0,
                min(asr["end"], sp["end"]) - max(asr["start"], sp["start"])
            )

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sp["speaker"]

        output.append(
            {
                "start": asr["start"],
                "end": asr["end"],
                "speaker": best_speaker,
                "text": asr["text"].strip(),
            }
        )

    return output


def process_audio(file_path: str, hf_token: str = None) -> List[Dict]:
    """Load, diarize, transcribe, and align. Returns the diarized segment list."""
    audio, sr = load_audio(file_path)

    print("Running speaker diarization...")
    diarization = run_diarization(audio, sr, hf_token)

    print("Running Whisper ASR...")
    asr_segments = run_asr(file_path)

    print("Assigning speakers to transcribed segments...")
    return assign_speakers_to_asr(diarization, asr_segments)


def run(audio_path: str, output_path: str) -> List[Dict]:
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    segments = process_audio(audio_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)
    print(f"Diarized transcript saved -> {output_path}")
    return segments


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 1: audio -> diarized JSON")
    parser.add_argument("audio_path")
    parser.add_argument("output_path")
    args = parser.parse_args()
    run(args.audio_path, args.output_path)