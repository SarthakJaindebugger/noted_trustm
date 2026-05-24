# Noted Backend

FastAPI backend for the Noted application. The backend manages session state, transcript persistence, summary generation, knowledge-base retrieval, and the WebSocket/REST APIs used by the frontend.

## Current Architecture

- FastAPI application entrypoint: `main.py`
- REST API: `/api/v1`
- WebSocket API: `/ws`
- Database: SQLite through async SQLAlchemy
- Batch transcription: lightweight local ASR (`faster-whisper`, tiny by default)
- Diarization: lightweight local fallback (single-speaker span) by default
- Summary generation: OpenAI-compatible `llama.cpp` model endpoint
- Retrieval: keyword matching plus Qdrant-backed embeddings

## Main Responsibilities

- create, update, and close sessions
- accept uploaded audio and live streamed audio
- batch audio for transcription
- persist transcript segments and session metadata
- generate final summaries and topic summaries
- retrieve relevant services from the knowledge base
- serve data back to the Vue frontend

## Configuration

Checked-in defaults live in `config.yaml`. Machine-specific values and secrets come from environment variables.

Common settings:

```bash
DOMAIN=localhost
DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///./noted.db
LLAMA_BASE_URL=http://llama-gen:8000/v1
LLAMA_API_KEY=none
SUMMARY_MODEL=gemma-4-26B-A4B-it-UD-Q4_K_M.gguf
UPLOAD_CHUNK_DURATION=300
ASR_BATCH_URL=http://lightweight-speech:8020
ASR_BATCH_MODEL=tiny
ASR_BATCH_CONCURRENCY=8
DIARIZATION_MODEL=local-simple
ASR_BATCH_MAX_TOKENS=24576
```

The backend code now uses the nested settings object directly, for example:

- `settings.server.port`
- `settings.audio.sample_rate`
- `settings.models.asr_batch.url`
- `settings.models.generation.url`
- `settings.rag.max_context_chars`

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the API directly:

```bash
python main.py
```

For full-stack local development, use the top-level `docker-compose.yml`.

## Key Paths

- `api/`: REST and WebSocket route handlers
- `audio/processor.py`: active audio processing pipeline
- `audio/chunker.py`: live audio buffering and chunking
- `services/`: session, embedding, and summarization services
- `database/`: models and connection setup
- `vector_db/`: Qdrant integration
- `knowledgebase/`: CSV data used for retrieval

## Notes For Collaborators

- The checked-in backend defaults are aligned with lightweight local ASR+diarization for no-key local runs
- If you are only working on the frontend, the backend contract to care about is the `/api/v1` and `/ws` surface, not the local model infrastructure.
