import os
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel
from speech_analysis_qa.speech_pipeline.common.device_utils import get_compute_device

app = FastAPI()

# Load tiny model (automatically downloads, no token required)
model_size = os.getenv("LIGHT_ASR_MODEL", "tiny")
requested_device = os.getenv("LIGHT_ASR_DEVICE", "auto")
compute_type = os.getenv("LIGHT_ASR_COMPUTE_TYPE", "int8")

device = get_compute_device(requested_device)

print(f"Loading {model_size} model on {device} with {compute_type}...")
model = WhisperModel(model_size, device=device, compute_type=compute_type)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/asr")
async def transcribe(file: UploadFile = File(...)):
    # Save temporarily
    temp_path = f"/tmp/{file.filename}"
    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    # Transcribe
    segments, info = model.transcribe(temp_path, beam_size=5)
    text = " ".join([seg.text for seg in segments])
    
    # Clean up
    os.remove(temp_path)
    
    return JSONResponse({"text": text})