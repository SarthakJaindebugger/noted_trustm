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
from typing import List, Dict

from common.config import HF_TOKEN, DIARIZATION_MODEL, WHISPER_MODEL_SIZE, TARGET_SAMPLE_RATE


def load_audio(file_path: str, target_sr: int = TARGET_SAMPLE_RATE):
    import librosa
    audio, sr = librosa.load(file_path, sr=target_sr, mono=True)
    return audio, sr


def run_diarization(audio, sr: int, token: str):
    import torch
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=token)
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    waveform = torch.from_numpy(audio).float().unsqueeze(0)
    return pipeline({"waveform": waveform, "sample_rate": sr})


def run_asr(audio_path: str, model_size: str = WHISPER_MODEL_SIZE) -> List[Dict]:
    import whisper

    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, word_timestamps=True)
    return result["segments"]


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
