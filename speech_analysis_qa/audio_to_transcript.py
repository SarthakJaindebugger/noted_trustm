"""Raw audio to diarized transcript using pyannote and Whisper."""

import os
from pathlib import Path
from typing import List

import librosa
import torch
import whisper
from pyannote.audio import Pipeline

from .config import AUDIO_DIR, DIARIZATION_MODEL, HF_TOKEN, LEGACY_AUDIO_DIR, WHISPER_MODEL
from .utils import normalize_text


class SpeechTranscriber:
    def __init__(self, hf_token: str = HF_TOKEN):
        self.hf_token = hf_token
        self.diarization_model = DIARIZATION_MODEL

    def load_audio(self, audio_path: Path, target_sr: int = 16000):
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        audio, sr = librosa.load(str(audio_path), sr=target_sr, mono=True)
        return audio, sr

    def default_audio_path(self, file_name: str) -> Path:
        candidate = AUDIO_DIR / file_name
        if candidate.exists():
            return candidate
        legacy_candidate = LEGACY_AUDIO_DIR / file_name
        if legacy_candidate.exists():
            return legacy_candidate
        raise FileNotFoundError(
            f"Neither preferred audio path {candidate} nor legacy path {legacy_candidate} exists"
        )

    def run_diarization(self, audio, sr):
        pipeline = Pipeline.from_pretrained(self.diarization_model, token=self.hf_token)
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        waveform = torch.from_numpy(audio).float().unsqueeze(0)
        return pipeline({"waveform": waveform, "sample_rate": sr})

    def run_asr(self, audio_path: Path):
        model = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(str(audio_path), word_timestamps=True)
        return result.get("segments", [])

    def assign_speakers(self, diarization, asr_segments: List[dict]) -> List[dict]:
        speaker_segments = []
        annotation = diarization.speaker_diarization
        for segment, _, speaker in annotation.itertracks(yield_label=True):
            speaker_segments.append({
                "start": segment.start,
                "end": segment.end,
                "speaker": speaker,
            })
        speaker_segments.sort(key=lambda item: item["start"])
        asr_segments.sort(key=lambda item: item.get("start", 0.0))

        output = []
        for asr in asr_segments:
            best_speaker = "UNKNOWN"
            best_overlap = 0.0
            for sp in speaker_segments:
                overlap = max(0.0, min(asr["end"], sp["end"]) - max(asr["start"], sp["start"]))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = sp["speaker"]
            output.append({
                "start": round(asr["start"], 3),
                "end": round(asr["end"], 3),
                "speaker": best_speaker,
                "text": normalize_text(asr.get("text", "")),
            })

        return output

    def transcribe(self, audio_path: Path) -> List[dict]:
        audio, sr = self.load_audio(audio_path)
        diarization = self.run_diarization(audio, sr)
        asr_segments = self.run_asr(audio_path)
        return self.assign_speakers(diarization, asr_segments)


def main():
    transcriber = SpeechTranscriber()
    default_audio = transcriber.default_audio_path("dia03sce1SA.wav")
    transcript = transcriber.transcribe(default_audio)
    print("Loaded", len(transcript), "segments")
    print(transcript[:3])


if __name__ == "__main__":
    main()
