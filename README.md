# Noted

Noted is a meeting capture and summary workspace for service-advice sessions. It combines a Vite frontend, a FastAPI backend, local ASR/diarization services, and retrieval-backed summary generation.

## Repository Layout

- `noted-frontend/`: web UI
- `noted-backend/`: FastAPI API, session state, transcripts, summaries, and retrieval
- `lightweight_speech_service/`: CPU-first ASR + fallback diarization service (no HF key)
- `knowledgebase/`: retrieval source data
- `docker-compose.yml`: local multi-service stack
- `SYSTEM_DESCRIPTION.md`: architecture notes

## Docker startup

### Full stack (Linux + NVIDIA GPU)

```bash
docker compose up --build
```

### macOS Apple Silicon + Ollama + local ASR/diarization (no HF API key)

This repository now includes a lightweight speech container that runs on CPU and does not require `HF_TOKEN`:
- ASR: `faster-whisper` (`tiny` by default)
- Diarization fallback: single-speaker segmentation (`SPEAKER_00`) so transcript pipeline keeps working

1. Start Ollama on host and pull model:

```bash
ollama pull llama3.1:8b-instruct
```

2. Run frontend/backend/qdrant/lightweight speech:

```bash
LLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
SUMMARY_MODEL=llama3.1:8b-instruct \
LLAMA_API_KEY=none \
docker compose up --build frontend backend qdrant lightweight-speech
```

Optional: slightly better ASR quality (slower)

```bash
LIGHT_ASR_MODEL=base docker compose up --build lightweight-speech backend frontend qdrant
```

## Health checks

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000/health`
- Lightweight speech: `http://127.0.0.1:8020/health` (inside docker network on `lightweight-speech:8020`)

## Notes

- GPU/HF-based services (`qwen3-asr`, `sortformer-diarizer`, `vllm-embed`) can still be used later by overriding URLs/env vars.
- If you need true multi-speaker diarization fully local (no token), accuracy will be lower than Sortformer/Pyannote unless you run heavier models.

## Backend-only development

See `noted-backend/README.md`.
