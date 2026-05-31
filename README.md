# Noted

Noted is a meeting capture and summary workspace for service-advice sessions. It combines a Vite-based frontend, a FastAPI backend, local ASR and diarization services, and retrieval-backed summary generation.

## Repository Layout

- `noted-frontend/`: web UI
- `noted-backend/`: FastAPI API, session state, transcripts, summaries, and retrieval
- `knowledgebase/`: source data used for retrieval
- `docker-compose.yml`: local multi-service development stack
- `SYSTEM_DESCRIPTION.md`: current architectural notes

## Local Development

Use the checked-in `.env.example` as the reference for required environment variables. Do not commit a real `.env` file or local database files.

For full-stack local development:

```bash
docker compose up --build
```

The generation model is served through `llama.cpp` on the shared Docker network `noted-llm-shared`. Other containers can reuse it by joining that network and calling `http://llama-gen:8000/v1`.

For backend-only work, see [noted-backend/README.md](/home/noted/noted-backend/README.md).

## Collaboration

This repository is intended to be shared through a fork-and-pull-request workflow:

- fork the private upstream repository
- create a feature branch in your fork
- open a pull request back to `main`
- wait for review before merge

Direct pushes to the upstream default branch should be blocked with GitHub branch protection.

## Before Publishing

- confirm `.env` stays untracked
- confirm local database files stay untracked
- confirm large local model assets are not committed
- update remotes so pushes go to your own GitHub repository, not the current upstream


# in .env.example: find passwords
# change this to Ollama api/host: http://llama-gen:8000/v1


# in docker-compose.yml : everything else for models/ Ollama
# in noted-backend/requirements.txt
# fastapi run main.py - should be the command later
# To change login creditials in backend: noted-backend/config.py




# Get the JSon output directly from the LLMs rather than parsing directly to CSV
# For Ollama JSON : https://docs.ollama.com/capabilities/structured-outputs