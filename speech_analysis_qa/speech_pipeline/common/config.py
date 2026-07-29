# -*- coding: utf-8 -*-
"""
common/config.py
=================
Single place for every constant, model name, path and credential used
anywhere in the pipeline. Every stage imports from here instead of
re-declaring its own copy of these values.

SECURITY NOTE
-------------
The original notebooks had Hugging Face tokens hard-coded as plain
strings. That has been removed. Set the token as an environment
variable before running anything, e.g.:

    export HF_TOKEN="hf_xxx..."

or put it in a local `.env` file that you load yourself and never commit.
"""

import os

# --------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# --------------------------------------------------------------------
# Stage 1 · Diarization + ASR
# --------------------------------------------------------------------
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
WHISPER_MODEL_SIZE = "base"          # "base" | "small" | "medium" | "large-v3"
TARGET_SAMPLE_RATE = 16000

# --------------------------------------------------------------------
# Stage 2 · Privacy / anonymisation
# --------------------------------------------------------------------
SPACY_MODEL = "en_core_web_lg"

REGEX_PATTERNS = {
    # Finnish personal identity code (ID card number)
    "FINNISH_HETU": r"\b\d{6}[+-A]\d{3}[0-9A-Y]\b",
    # Passport number (1-2 letters + 6-9 digits)
    "PASSPORT": r"\b[A-Z]{1,2}[0-9]{6,9}\b",
    # Phone number
    "PHONE": r"(\+?\d[\d\s\-]{7,}\d)",
}

PLACEHOLDER_NOTE = """
    <PERSON_1>, <PERSON_2>, ...     -> a person's name
    <FINNISH_HETU_1>                -> a Finnish personal identity code / ID card number
    <PASSPORT_1>                    -> a passport number
    <PHONE_1>                       -> a phone number

    These are the ONLY categories of information that have been anonymized/replaced
    with placeholders. Everything else in the transcript -- including city, country,
    dates, organizations, job details, education, family situation, reasons for the
    visit, etc. -- is UNCHANGED original text (real words, not placeholders) and
    should be read and used normally.

    IMPORTANT -- addresses and locations are NOT anonymized:
    - Full street addresses have been shortened to just city + country, but the
      city and country themselves are left as plain, real text (e.g. "Espoo, Finland"),
      never turned into a placeholder like <CITY_1> or <COUNTRY_1>.

    Rules for the placeholders that DO exist (PERSON, FINNISH_HETU, PASSPORT, PHONE):
    - Treat each placeholder exactly as the original value it stands for.
    - Never replace a placeholder with words like anonymous/unknown/redacted/hidden.
    - Never invent, guess, or reconstruct the original value behind a placeholder.
    - Never omit or alter a placeholder when it belongs in an answer -- copy it exactly
      as written (including the angle brackets and number), e.g. <PERSON_1>.
"""

# --------------------------------------------------------------------
# Stage 3 · Metadata (speaker roles + speaking time)
# --------------------------------------------------------------------
# Qwen chat model used for speaker-role identification and structured Q&A.
MODEL_NAME = "Qwen/Qwen3-8B"

ROLE_ID_MODEL_NAME = MODEL_NAME
ROLE_ADVISOR = "advisor"
ROLE_CUSTOMER = "customer"

# --------------------------------------------------------------------
# Stage 4 · Structured Q&A over the private transcript
# --------------------------------------------------------------------
QA_MODEL_NAME = MODEL_NAME
EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-4B"

# The prompts contain the questionnaire and instructions, so use retrieval for
# all but very short transcripts and provide compact excerpts per prompt.
CHUNK_SIZE = 500
OVERLAP = 75
TOP_K = 2
MAX_CHARS_FOR_FULL_CONTEXT = 1800

# --------------------------------------------------------------------
# Output file names (all stages write into one run folder)
# --------------------------------------------------------------------
DIARIZED_JSON_NAME = "1_diarized_transcript.json"
PRIVATE_TRANSCRIPT_JSON_NAME = "2_private_transcript.json"
MAPPING_JSON_NAME = "2_mapping.json"
METADATA_JSON_NAME = "3_metadata.json"
PRIVATE_RESULTS_JSON_NAME = "4_private_results.json"
MAPPED_RESULTS_JSON_NAME = "5_mapped_results.json"
