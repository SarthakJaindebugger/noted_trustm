# Audio -> Mapped JSON Pipeline

## Command to run: python3 speech_analysis_qa/speech_pipeline/run_pipeline.py --all-users

Restructured from the 4 original Colab notebooks into 6 sequential stages
with no duplicated code. Shared logic (LLM calling, JSON parsing,
transcript flattening, anonymization, retrieval) lives once in `common/`
and every stage imports it instead of redefining it.

```
pipeline/
├── common/
│   ├── config.py            # every constant/model name/path/token in one place
│   ├── text_utils.py        # segments_to_text, chunk_text, format_seconds
│   ├── json_utils.py        # clean_answer, extract_json (LLM output parsing)
│   ├── llm_utils.py         # load_llm, ask_question (used by stage 3 & 4)
│   ├── retrieval_utils.py   # Retriever: embed + in-memory Qdrant (stage 4 only)
│   ├── privacy_utils.py     # PlaceholderMapper: regex + spaCy NER anonymization (stage 2)
│   └── questions.py         # the structured questionnaire, as data (stage 4)
│
├── stage1_diarize_transcribe.py   # 1) raw audio       -> 2) pyannote JSON
├── stage2_privacy.py              #    pyannote JSON    -> 3) private transcript + mapping.json
├── stage3_metadata.py             #    private transcript -> 4) metadata JSON
├── stage4_qa_private.py           #    private transcript -> 5) private Q&A JSON
├── stage5_apply_mapping.py        #    private Q&A + mapping -> 6) mapped (final) JSON
└── run_pipeline.py                # orchestrates all of the above
```

## The 6 stages

1. **Input raw audio** — a `.wav`/`.mp3`/etc. file you provide.
2. **pyannote JSON** — `stage1_diarize_transcribe.py` runs pyannote
   diarization + Whisper ASR and aligns them into
   `[{"start", "end", "speaker", "text"}, ...]`.
3. **Privacy JSON + mapping** — `stage2_privacy.py` anonymizes names,
   Finnish HETU codes, passport numbers, and phone numbers, and shortens
   addresses to city/country. Produces `2_private_transcript.json` and
   `2_mapping.json` (placeholder -> original value).
4. **Metadata JSON** — `stage3_metadata.py` asks the LLM which raw
   speaker label is the advisor and which is the customer, then sums
   segment durations per role. It exposes **two separate variables**:
   `total_advisor_time_sec` and `total_customer_time_sec` (also returned
   from `run()` and saved in the JSON as `total_advisor_time_sec` /
   `total_customer_time_sec`, plus human-readable `total_advisor_time`
   / `total_customer_time` strings).
5. **Questions & answers JSON (private)** — `stage4_qa_private.py` runs
   the structured questionnaire (`common/questions.py`) plus summary,
   "Additional Information" and "Feedback" fields over the private
   transcript using retrieval-augmented context. Output still contains
   `<PERSON_1>`-style placeholders.
6. **Mapped JSON** — `stage5_apply_mapping.py` applies `mapping.json` to
   the stage-5 output, replacing every placeholder with its real value,
   producing the final de-anonymized result.

## Running it

```bash
export HF_TOKEN="hf_xxx..."          # required, no tokens are hard-coded anymore
python3 run_pipeline.py /path/to/audio.wav /path/to/output_dir
```

This writes, into `output_dir`:

```
1_diarized_transcript.json
2_private_transcript.json
2_mapping.json
3_metadata.json
4_private_results.json
5_mapped_results.json
```

Each stage can also be run on its own from the command line (see the
`if __name__ == "__main__":` block at the bottom of each `stage*.py`
file), so you can re-enter the pipeline at any point without re-running
earlier stages.

## What changed vs. the original 4 notebooks

- **No hard-coded HF tokens.** They were plaintext in all 4 original
  files; now everything reads `HF_TOKEN` from the environment
  (`common/config.py`).
- **One `ask_question`, not three.** `pyannote_to_json.py` and
  `privacy_rag_2_outputs.py` each had their own near-identical chat-LLM
  helper; now there's one in `common/llm_utils.py`.
- **One `extract_json`/`clean_answer`,** not separate copies in
  `privacy_rag_2_outputs.py` and `audio_to_csv_json.py`.
- **One "flatten segments to text" function**, not duplicated in
  `pyannote_to_json.py` and `privacy_rag_2_outputs.py`.
- **Advisor/customer role identification moved out of an ad-hoc, one-off
  prompt** buried in `pyannote_to_json.py` and turned into a proper
  stage-3 function whose output (speaking-time totals) is what the user
  actually needs downstream.
- `audio_to_csv_json.py`'s RAG-embeddings-to-parquet feature (mostly
  commented-out code in the original file, and not part of the
  audio -> mapped-JSON path the user asked for) was left out of this
  pipeline; the retrieval used by stage 4 is a self-contained in-memory
  index instead, scoped only to what stage 4 needs.

## Requirements

```
pip install pyannote.audio openai-whisper torchaudio librosa soundfile
pip install spacy && python -m spacy download en_core_web_lg
pip install transformers accelerate bitsandbytes qdrant-client
```

A GPU is strongly recommended for stages 1, 3, and 4.
