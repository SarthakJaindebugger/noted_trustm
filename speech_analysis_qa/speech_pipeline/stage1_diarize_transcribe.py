# -*- coding: utf-8 -*-
"""
Stage 1 · Input Raw Audio -> Diarized/Transcribed JSON
=========================================================
Runs pyannote speaker diarization + Whisper ASR on a raw audio file and
aligns the two into one list of {"start", "end", "speaker", "text"}
segments ("the pyannote json").

Refactored from pyannote_to_json.py's ASR + SEGMENTATION section.
Everything unrelated to that (the age/gender wav2vec2 experiments, the
ad-hoc "identify advisor/customer" prompt) has moved to stage 3, where it
belongs, instead of living inline here.
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict

PIPELINE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = PIPELINE_DIR.parent
REPO_ROOT = PACKAGE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from speech_analysis_qa.speech_pipeline.common.config import HF_TOKEN, DIARIZATION_MODEL, WHISPER_MODEL_SIZE, TARGET_SAMPLE_RATE

_DIARIZATION_PIPELINE = None
_WHISPER_MODEL_CACHE = {}


def _get_diarization_pipeline(token: str):
    global _DIARIZATION_PIPELINE
    if _DIARIZATION_PIPELINE is None:
        from pyannote.audio import Pipeline

        auth_kwargs = {}
        if token:
            auth_kwargs["token"] = token

        _DIARIZATION_PIPELINE = Pipeline.from_pretrained(
            DIARIZATION_MODEL,
            **auth_kwargs,
        )
    return _DIARIZATION_PIPELINE


def _get_whisper_model(model_size: str = WHISPER_MODEL_SIZE):
    global _WHISPER_MODEL_CACHE
    if model_size not in _WHISPER_MODEL_CACHE:
        import torch
        from faster_whisper import WhisperModel

        # faster-whisper does not support MPS on this environment, so fall back to CPU.
        device = "cpu"
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
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
        except Exception:
            pass


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


def assign_speakers_to_asr(diarization, asr_segments: List[Dict]) -> List[Dict]:
    annotation = diarization.speaker_diarization

    speaker_segments = [
        {"start": segment.start, "end": segment.end, "speaker": speaker}
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]
    speaker_segments.sort(key=lambda x: x["start"])
    asr_segments = sorted(asr_segments, key=lambda x: x["start"])

    output = []
    for asr in asr_segments:
        best_overlap, best_speaker = 0, "UNKNOWN"
        for sp in speaker_segments:
            overlap = max(0, min(asr["end"], sp["end"]) - max(asr["start"], sp["start"]))
            if overlap > best_overlap:
                best_overlap, best_speaker = overlap, sp["speaker"]

        output.append({
            "start": asr["start"],
            "end": asr["end"],
            "speaker": best_speaker,
            "text": asr["text"].strip(),
        })
    return output


def process_audio(file_path: str, hf_token: str = HF_TOKEN) -> List[Dict]:
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
