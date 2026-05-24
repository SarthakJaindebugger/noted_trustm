import io
import os
import tempfile
from typing import List, Dict

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from faster_whisper import WhisperModel

app = FastAPI(title="Lightweight Speech Service", version="0.1.0")

MODEL_SIZE = os.getenv("LIGHT_ASR_MODEL", "tiny")
COMPUTE_TYPE = os.getenv("LIGHT_ASR_COMPUTE_TYPE", "int8")
DEVICE = os.getenv("LIGHT_ASR_DEVICE", "cpu")

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def audio_duration_seconds(data: bytes) -> float:
    try:
        arr, sr = sf.read(io.BytesIO(data), always_2d=False)
        if isinstance(arr, np.ndarray) and arr.ndim > 1:
            arr = np.mean(arr, axis=1)
        return float(len(arr) / float(sr)) if sr else 0.0
    except Exception:
        return 0.0


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "lightweight_speech"}


@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile = File(...), model: str = Form(default="tiny")):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        segments, _ = get_model().transcribe(tmp.name, beam_size=1, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip()).strip()

    return {"text": text}


@app.post("/diarize")
async def diarize(file: UploadFile = File(...), model: str = Form(default="local-simple"), max_speakers: int = Form(default=2)) -> List[Dict]:
    data = await file.read()
    if not data:
        return []

    duration = audio_duration_seconds(data)
    if duration <= 0:
        return []

    # Lightweight fallback diarization: single-speaker full-span segment.
    return [{"start": 0.0, "end": round(duration, 3), "speaker": "SPEAKER_00"}]
