FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install faster-whisper (CPU‑optimised, no HF token needed for tiny model)
RUN pip install --no-cache-dir fastapi uvicorn faster-whisper python-multipart

COPY lightweight_speech_server.py .

EXPOSE 8020

CMD ["uvicorn", "lightweight_speech_server:app", "--host", "0.0.0.0", "--port", "8020"]