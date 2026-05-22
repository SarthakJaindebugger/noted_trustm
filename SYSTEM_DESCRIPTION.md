# Noted System Description

## Overview

Noted is a meeting capture and summary system for service-advice sessions. The product records or uploads audio, produces diarized transcripts, stores session data in SQLite, retrieves related services from a knowledge base, and generates structured customer-facing summaries with local model endpoints.

The repository is organized as an application workspace rather than a minimal package. For GitHub sharing, the source code that matters lives primarily in `noted-frontend/`, `noted-backend/`, and the top-level Docker files.

## Current Stack

- Frontend: Vue 3, Vue Router, Pinia, Vite, Tailwind CSS 4
- Backend: FastAPI, SQLAlchemy async, Instructor, OpenAI-compatible model clients
- Batch ASR: Qwen3-ASR 0.6B served through vLLM
- Diarization: NVIDIA Sortformer served through a local FastAPI wrapper
- Summary model: Gemma GGUF served through `llama-gen` (`llama.cpp`)
- Embeddings: Qwen embedding model served through `vllm-embed`
- Vector store: Qdrant
- Persistence: SQLite
- Orchestration: Docker Compose

## Repository Layout

- `noted-frontend/`: active frontend app, built with Vite and served by Nginx in production
- `noted-backend/`: FastAPI backend, transcript/session management, summarization, and RAG logic
- `knowledgebase/`: CSV knowledge sources mounted into the backend
- `docker-compose.yml`: local multi-service orchestration
- `sortformer.Dockerfile`, `LlamaCPP/Dockerfile`: model-service container builds

Large local runtime assets such as model weights, Qdrant storage, recordings, and `.env` secrets are intentionally treated as local-only and should not be committed.

## Frontend Notes

The active frontend entrypoint is `noted-frontend/index.html`. The application boots from `noted-frontend/js/main.js` and routes through `noted-frontend/js/router.js`.

Important frontend areas:

- `js/components/dashboard.js`: session list and session detail UI
- `js/components/recording_view.js`: live recording flow
- `js/components/new_session.js`: start/upload flow
- `js/components/crm_form.js`: structured follow-up form
- `js/services/`: backend API clients
- `js/stores/`: auth and session state

The frontend no longer relies on a global Vue compatibility shim; components should use normal module imports from `vue`.

## Backend Notes

The backend starts in `noted-backend/main.py` and exposes:

- REST endpoints under `/api/v1`
- WebSocket endpoints under `/ws`
- health endpoint at `/health`

Core backend responsibilities:

- manage session lifecycle and transcript persistence
- buffer incoming audio and batch it for transcription
- normalize transcript text and persist segments
- retrieve related services from the knowledge base and Qdrant
- generate final summaries and topic summaries

The main runtime pipeline is:

1. frontend streams or uploads audio
2. backend buffers audio chunks
3. backend diarizes uploaded audio with Sortformer, then sends speaker turns to Qwen3-ASR for transcription
4. transcript entries are stored in SQLite and pushed to clients
5. summary and topic generation call local OpenAI-compatible model endpoints
6. related services are retrieved through keyword and embedding search

## Configuration

Runtime configuration comes from:

- `noted-backend/config.yaml` for checked-in defaults
- `.env` for secrets and machine-specific overrides
- `docker-compose.yml` for container wiring

`config.py` expects code to use the nested settings structure directly, for example:

- `settings.server.port`
- `settings.audio.sample_rate`
- `settings.models.generation.url`
- `settings.rag.max_context_chars`
