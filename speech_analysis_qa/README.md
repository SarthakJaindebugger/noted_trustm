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



# AGE GENDER MODEL
https://github.com/audeering/w2v2-age-gender-how-to