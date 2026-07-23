# speech_analysis_qa

A modular speech analysis and RAG pipeline for audio-to-transcript, speaker-aware chunking, embeddings, retrieval, and Qwen-based question answering.

Structure:
- `audio_to_transcript.py`: raw audio -> diarized transcript JSON
- `transcript_chunking.py`: speaker-aware chunking + overlap handling
- `embeddings.py`: Qwen embedding wrapper + batching
- `retrieval.py`: Qdrant collection creation + similarity search
- `rag.py`: retrieval-augmented generation orchestration + prompt builder
- `config.py`: shared defaults and configuration helpers
- `utils.py`: shared utility functions and JSON loaders
- `speech_pipeline/run_pipeline.py`: end-to-end speech analysis pipeline and per-user batch runner

## User data flow

The pipeline expects the application user data layout under:

```text
knowledgebase/users_admin_data/users/<username>/
├── recordings/   # input audio files
├── uploads/      # generated transcript, mapping, metadata, private Q&A, mapped Q&A JSON
└── embedding/    # generated chunk embedding JSON files and embedding manifest
```

Run all users:

```bash
python speech_analysis_qa/speech_pipeline/run_pipeline.py --all-users
```

Run one user:

```bash
python speech_analysis_qa/speech_pipeline/run_pipeline.py --user alice
```

For each recording, pipeline JSON outputs are written to `uploads/<audio_stem>/`, while speaker-aware chunks are embedded and written to `embedding/<audio_stem>_chunk<N>_embedding.json` with a manifest at `embedding/<audio_stem>_embedding_manifest.json`. The same chunks are also upserted to Qdrant for later RAG retrieval.


# AGE GENDER MODEL
https://github.com/audeering/w2v2-age-gender-how-to
