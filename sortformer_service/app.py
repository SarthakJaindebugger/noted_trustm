from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

logger = logging.getLogger("sortformer_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Sortformer Diarizer")

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        try:
            from nemo.collections.asr.models import SortformerEncLabelModel
            import torch
        except Exception as exc:
            raise RuntimeError(f"Failed to import NeMo Sortformer: {exc}") from exc

        model_name = os.getenv("SORTFORMER_MODEL", "nvidia/diar_streaming_sortformer_4spk-v2.1")
        requested_device = os.getenv("DIARIZATION_DEVICE", "auto").strip().lower() or "auto"
        if requested_device == "auto":
            map_location = "cuda" if torch.cuda.is_available() else "cpu"
        elif requested_device.startswith("cuda") and not torch.cuda.is_available():
            logger.warning("CUDA requested for Sortformer, but torch.cuda.is_available() is false. Falling back to CPU.")
            map_location = "cpu"
        elif requested_device == "mps":
            map_location = "cpu"
        else:
            map_location = "cpu" if requested_device == "cpu" else requested_device

        logger.info("Loading Sortformer model %s on %s", model_name, map_location)
        model = SortformerEncLabelModel.from_pretrained(model_name, map_location=map_location)
        model.eval()

        _model = model
        return _model


def _normalize_segments(raw_segments: Any) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []

    def _speaker_label(raw_value: Any) -> str:
        text = str(raw_value).strip()
        if text.startswith("speaker_"):
            return text
        match = re.search(r"(\d+)$", text)
        if match:
            return f"speaker_{int(match.group(1)):02d}"
        return f"speaker_{text}" if text else "speaker_00"

    def _visit(item: Any) -> None:
        if isinstance(item, dict):
            if {"start", "end"} <= set(item.keys()):
                speaker = item.get("speaker", item.get("label", item.get("speaker_id", "speaker_00")))
                segments.append({
                    "start": float(item.get("start", 0.0)),
                    "end": float(item.get("end", item.get("start", 0.0))),
                    "speaker": _speaker_label(speaker),
                    "confidence": float(item.get("confidence", 0.0) or 0.0),
                })
                return
            for value in item.values():
                _visit(value)
            return

        if isinstance(item, (list, tuple)):
            if len(item) == 3 and all(isinstance(v, (int, float, str)) for v in item):
                start_raw, end_raw, speaker_raw = item
                try:
                    start = float(start_raw)
                    end = float(end_raw)
                except Exception:
                    start = 0.0
                    end = 0.0
                segments.append({
                    "start": start,
                    "end": end,
                    "speaker": _speaker_label(speaker_raw),
                    "confidence": 0.0,
                })
                return
            for value in item:
                _visit(value)
            return

        if isinstance(item, str):
            parts = [part for part in re.split(r"[\s,]+", item.strip()) if part]
            if len(parts) >= 3:
                try:
                    start = float(parts[0])
                    end = float(parts[1])
                    speaker = _speaker_label(parts[2])
                except Exception:
                    return
                segments.append({
                    "start": start,
                    "end": end,
                    "speaker": speaker,
                    "confidence": 0.0,
                })

    _visit(raw_segments)

    normalized = [segment for segment in segments if segment["end"] > segment["start"]]
    normalized.sort(key=lambda segment: (segment["start"], segment["end"]))
    return normalized


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/diarize")
async def diarize(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    model: str = Form(default=""),
    max_speakers: int = Form(default=2),
):
    del session_id, model, max_speakers

    diarizer = _get_model()
    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        predicted_segments = diarizer.diarize(audio=tmp_path, batch_size=1)
        segments = _normalize_segments(predicted_segments)
        if not segments:
            raise HTTPException(status_code=502, detail="Diarizer returned no segments")
        return {"segments": segments}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Sortformer diarization failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
