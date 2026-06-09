
# print("✅  Packages ready.")


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 2 · ⚙️  CONFIGURATION  ← only edit this cell
# # ──────────────────────────────────────────────────────────────────────────

# # HuggingFace token — https://huggingface.co/settings/tokens
# # Accept the LLaMA licence at:  https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
# HF_API_KEY = "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"          # ← FILL IN

# # Upload your audio via the Colab Files sidebar, then set the path here.
# # Supported formats: .wav  .mp3  .m4a  .ogg  .flac
# AUDIO_PATH = "/content/dia03sce2SA.wav"     # ← FILL IN

# # Where to write the output JSON
# OUTPUT_JSON_PATH = "/content/visit_log_dia03sce2SA.json"

# LLAMA_MODEL  = "meta-llama/Llama-3.1-8B-Instruct"
# WHISPER_SIZE = "large-v3"   

# print("✅  Config loaded.")
# print(f"    Model  : {LLAMA_MODEL}")
# print(f"    Whisper: {WHISPER_SIZE}")
# print(f"    Audio  : {AUDIO_PATH}")


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 3 · Imports
# # ──────────────────────────────────────────────────────────────────────────

# import os, re, json, torch
# from datetime import datetime
# from huggingface_hub import InferenceClient
# import pandas as pd
# from pathlib import Path
# print("✅  Imports done.")


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 4 · Transcribe with Whisper
# # ──────────────────────────────────────────────────────────────────────────

# def transcribe(audio_path: str, model_size: str = "large-v3") -> tuple:
#     """
#     Transcribe audio with faster-whisper.
#     Returns (full_text: str, segments: list[dict], whisper_meta: dict)

#     Each segment dict:  { "start": float, "end": float, "text": str }
#     """
#     from faster_whisper import WhisperModel

#     if not os.path.exists(audio_path):
#         raise FileNotFoundError(
#             f"\n❌  Audio file not found: {audio_path}\n"
#             "    Upload it via the Files panel (left sidebar in Colab),\n"
#             "    then update AUDIO_PATH in Cell 2."
#         )

#     device  = "cuda" if torch.cuda.is_available() else "cpu"
#     compute = "float16" if device == "cuda" else "int8"
#     print(f"  Device  : {device}  ({compute})")
#     print(f"  Loading : Whisper {model_size}")

#     wmodel = WhisperModel(model_size, device=device, compute_type=compute)

#     gen, info = wmodel.transcribe(
#         audio_path,
#         beam_size=5,
#         vad_filter=True,
#         vad_parameters=dict(min_silence_duration_ms=400),
#         language=None,   # auto-detect
#     )

#     segments, texts = [], []
#     for seg in gen:
#         texts.append(seg.text)
#         segments.append({
#             "start": round(seg.start, 2),
#             "end":   round(seg.end, 2),
#             "text":  seg.text.strip(),
#         })

#     full_text = " ".join(texts).strip()
#     full_text = re.sub(r"\s+", " ", full_text)                   # collapse spaces
#     full_text = re.sub(r"(\w)\s*-\s*(\w)", r"\1\2", full_text)  # fix split-word ASR artefacts

#     duration_sec = round(segments[-1]["end"] if segments else 0, 1)
#     whisper_meta = {
#         "language":             info.language,
#         "language_probability": round(info.language_probability, 3),
#         "duration_sec":         duration_sec,
#         "segment_count":        len(segments),
#         "char_count":           len(full_text),
#     }

#     print(f"  Language: {info.language}  (p={info.language_probability:.2f})")
#     print(f"  Duration: {duration_sec}s  |  {len(segments)} segments  |  {len(full_text)} chars")
#     return full_text, segments, whisper_meta


# # ── Run ───────────────────────────────────────────────────────────────────
# print("🎙️  Transcribing...\n")
# transcript, segments, whisper_meta = transcribe(AUDIO_PATH, WHISPER_SIZE)

# print(f"\n📝  Transcript preview (first 600 chars):\n{'─'*60}")
# print(transcript[:600] + ("..." if len(transcript) > 600 else ""))
# print("─"*60)


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 5 · LLaMA helper — one reusable function for all LLM calls
# # ──────────────────────────────────────────────────────────────────────────

# def call_llama(
#     system_prompt : str,
#     user_prompt   : str,
#     hf_api_key    : str,
#     model         : str   = "meta-llama/Llama-3.1-8B-Instruct",
#     max_tokens    : int   = 2048,
#     temperature   : float = 0.15,
# ) -> str:
#     """
#     Single reusable wrapper for every LLaMA call in this notebook.
#     Returns the raw string content from the model.
#     Raises clearly on auth or connection errors.
#     """
#     if not hf_api_key or hf_api_key.startswith("hf_YOUR"):
#         raise ValueError(
#             "❌  HF_API_KEY is not set.\n"
#             "    Get a token at https://huggingface.co/settings/tokens\n"
#             "    and paste it into HF_API_KEY in Cell 2."
#         )

#     client = InferenceClient(token=hf_api_key)

#     response = client.chat.completions.create(
#         model=model,
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user",   "content": user_prompt},
#         ],
#         max_tokens=max_tokens,
#         temperature=temperature,
#         top_p=0.9,
#     )

#     return response.choices[0].message.content.strip()


# def parse_json_from_llm(raw: str) -> dict:
#     """
#     Robustly extract a JSON object from an LLM response.
#     Handles stray markdown fences and leading/trailing text.
#     """
#     # Remove markdown code fences
#     cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

#     # Find the outermost { ... } block
#     json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
#     if not json_match:
#         return {"_error": "No JSON object found", "_raw": raw}

#     try:
#         return json.loads(json_match.group(0))
#     except json.JSONDecodeError as e:
#         return {"_error": str(e), "_raw": raw}


# print("✅  LLaMA helper ready.")


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 6 · Step 1 — Detailed summary
# #
# # A dedicated summarisation call produces a rich narrative summary.
# # This is a separate LLM pass from the structured extraction so each
# # prompt can be tuned independently without tradeoffs.
# #
# # The summary prompt asks for six named sections so the output is
# # consistently structured even in prose form.
# # ──────────────────────────────────────────────────────────────────────────

# SUMMARY_SYSTEM = """\
# You are an expert case-notes writer for a Finnish immigrant guidance and integration service.
# You write clear, accurate, and detailed summaries of customer visits based on
# speech-recognition transcripts.

# The transcript may be noisy (ASR errors, disfluencies, incomplete sentences).
# Read for meaning, not literal wording.
# Write in professional English. Be specific — include names, ages, places, services,
# and decisions mentioned. Do not invent anything not in the transcript."""

# SUMMARY_USER = """\
# Below is the full speech-recognition transcript of a customer visit.

# <transcript>
# {transcript}
# </transcript>

# Write a detailed summary of this visit with the following six sections.
# Use plain prose under each heading — no bullet points inside sections.

# ## 1. Customer Profile
# Who is the customer? Include gender, approximate age or family situation,
# country of origin or background, language skills, and how long they have
# been in Finland — based only on what is mentioned in the transcript.

# ## 2. Reason for Visit
# Why did the customer come to the service today?
# What specific question or problem brought them in?

# ## 3. Topics Discussed
# What topics and subjects came up during the conversation?
# Describe each topic in a sentence or two, covering what the customer asked
# and what angle the conversation took.

# ## 4. Guidance and Information Provided
# What information, advice, or guidance was given to the customer?
# Be specific: mention services named, steps explained, documents referred to,
# websites or phone numbers mentioned, eligibility conditions discussed, etc.

# ## 5. Referrals and Next Steps
# What services or organisations was the customer referred to?
# What actions does the customer need to take next?
# What follow-up is expected?

# ## 6. Additional Observations
# Note anything else relevant: customer's emotional state if apparent,
# communication challenges, outstanding questions not fully resolved,
# or anything unusual about the visit."""


# def generate_summary(transcript: str) -> str:
#     print("  Sending summary prompt...")
#     raw = call_llama(
#         system_prompt = SUMMARY_SYSTEM,
#         user_prompt   = SUMMARY_USER.format(transcript=transcript),
#         hf_api_key    = HF_API_KEY,
#         model         = LLAMA_MODEL,
#         max_tokens    = 1500,
#         temperature   = 0.20,   # slightly higher — prose benefits from some variation
#     )
#     print(f"  ✅  Summary received ({len(raw)} chars)")
#     return raw


# # ── Run ───────────────────────────────────────────────────────────────────
# print("📝  Generating detailed summary...\n")
# summary_text = generate_summary(transcript)

# print("\n" + "═"*70)
# print("  📄  DETAILED SUMMARY")
# print("═"*70)
# print(summary_text)
# print("═"*70)


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 7 · Step 2 — Structured field extraction
# #
# # ──────────────────────────────────────────────────────────────────────────

# EXTRACTION_SYSTEM = """\
# You are a structured data extraction assistant for a Finnish immigrant guidance service.
# Extract specific fields from a noisy speech-recognition transcript of a customer visit.

# Rules:
# - Interpret semantic meaning, not literal wording. Transcripts are noisy.
# - If a field is NOT present in the transcript: write "No information" (categorical)
#   or "Not specified" (free text). Never guess or invent.
# - Pronoun rule: she / her / mother → Gender = Woman.  he / his / father → Gender = Man.
# - Topics: list ALL explicitly discussed topics, separated by semicolons.
# - Return ONLY a valid JSON object. No markdown. No code fences. No extra text."""


# def build_extraction_prompt(transcript: str, duration_sec: float) -> str:
#     mins = int(duration_sec // 60)
#     secs = int(duration_sec % 60)
#     duration_label = f"{mins} min {secs} sec" if mins > 0 else f"{secs} sec"

#     return f"""\
# Transcript of a customer visit to an immigrant guidance service:

# <transcript>
# {transcript}
# </transcript>

# Fill in every field in the JSON template below.
# Use only the options shown in angle brackets, or write "No information" / "Not specified".

# {{
#   "Gender":
#     "<Woman | Man | Non-binary | No information>",

#   "Age_Group":
#     "<Child 0-12 | Teenager 13-17 | Young adult 18-29 | Adult 30-64 | Senior 65+ | No information>
#      If customer has a child, append child age: e.g. 'Adult 30-64 (parent of 3-year-old)'",

#   "Reason_for_Immigration":
#     "<Work | Family reunification | Refugee / Asylum seeker | Student | Other | No information>",

#   "Labor_Market_Position":
#     "<Working in the open market | Unemployed job seeker | Student | On parental leave | Retired | No information>",

#   "Customers_Domicile":
#     "<Finnish city name, or 'Not specified'>",

#   "Duration_of_Residence_in_Finland":
#     "<Less than 3 months | Less than 1 year | 1-3 years | 3-5 years | More than 5 years | No information>",

#   "Country_of_Birth":
#     "<country name, or 'Not specified'>",

#   "Mother_Tongue":
#     "<language name(s), or 'Not specified'>",

#   "Finnish_Language_Skills":
#     "<None | Basic | Conversational | Fluent | Not mentioned>",

#   "Education_Level":
#     "<Primary / basic | Secondary | Vocational | University / higher | No information>",

#   "Topics_Discussed":
#     "<semicolon-separated topics — e.g. 'Early childhood education; Kela benefits; Residence permit'>",

#   "Number_of_People_in_Household":
#     "<integer, or 'Not specified'>",

#   "How_Customer_Heard_About_Service":
#     "<word of mouth | online search | referral from another service | signage | not mentioned>",

#   "Services_Sought":
#     "<what the customer was specifically looking for — 1-2 sentences>",

#   "Guidance_Provided":
#     "<what guidance or information was given — 1-2 sentences>",

#   "Referrals_Made":
#     "<organisations or services the customer was referred to, or 'None mentioned'>",

#   "Confidence_Notes":
#     "<fields you are uncertain about and why, or 'All fields extracted with reasonable confidence'>"
# }}

# Estimated visit duration from audio: {duration_label}
# Date: {datetime.now().strftime("%d/%m/%Y")}"""


# def extract_fields(transcript: str, duration_sec: float) -> dict:
#     print("  Sending extraction prompt...")
#     raw = call_llama(
#         system_prompt = EXTRACTION_SYSTEM,
#         user_prompt   = build_extraction_prompt(transcript, duration_sec),
#         hf_api_key    = HF_API_KEY,
#         model         = LLAMA_MODEL,
#         max_tokens    = 1200,
#         temperature   = 0.05,   # near-deterministic for structured output
#     )
#     print(f"  Raw response: {len(raw)} chars")
#     parsed = parse_json_from_llm(raw)

#     if "_error" in parsed:
#         print(f"  ⚠️  JSON parse failed: {parsed['_error']}")
#         print("  Raw LLM output saved in _raw field.")
#     else:
#         print(f"  ✅  Parsed — {len(parsed)} fields extracted")

#     return parsed


# # ── Run ───────────────────────────────────────────────────────────────────
# print("🔍  Extracting structured fields...\n")
# extraction = extract_fields(transcript, whisper_meta["duration_sec"])

# print("\n" + "═"*70)
# print("  🗂️   STRUCTURED EXTRACTION (raw JSON)")
# print("═"*70)
# print(json.dumps(extraction, indent=2, ensure_ascii=False))
# print("═"*70)



# def assemble_output(
#     transcript   : str,
#     segments     : list,
#     whisper_meta : dict,
#     summary_text : str,
#     extraction   : dict,
#     audio_path   : str,
# ) -> dict:
#     """
#     Assemble all pipeline outputs into a single clean JSON-serialisable dict.
#     """
#     mins = int(whisper_meta["duration_sec"] // 60)
#     secs = int(whisper_meta["duration_sec"]  % 60)

#     return {
#         "metadata": {
#             "date_time":            datetime.now().strftime("%d/%m/%Y %H:%M"),
#             "visit_duration":       f"{mins} min {secs} sec",
#             "audio_file":           os.path.basename(audio_path),
#             "whisper_model":        WHISPER_SIZE,
#             "llm_model":            LLAMA_MODEL,
#             "detected_language":    whisper_meta["language"],
#             "language_probability": whisper_meta["language_probability"],
#             "audio_duration_sec":   whisper_meta["duration_sec"],
#             "transcript_char_count": whisper_meta["char_count"],
#             "segment_count":        whisper_meta["segment_count"],
#         },

#         "summary": summary_text,

#         "extraction": extraction,

#         "transcript": {
#             "full_text": transcript,
#             "segments":  segments,      # each: { start, end, text }
#         },
#     }


# final_output = assemble_output(
#     transcript   = transcript,
#     segments     = segments,
#     whisper_meta = whisper_meta,
#     summary_text = summary_text,
#     extraction   = extraction,
#     audio_path   = AUDIO_PATH,
# )

# # Save
# with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
#     json.dump(final_output, f, indent=2, ensure_ascii=False)


# def json_to_qa_table(data, output_dir):
#     """
#     Convert extraction output into QA CSV.
#     """

#     metadata = data.get("metadata", {})
#     extraction = data.get("extraction", {})

#     def get_value(key, default="Not specified"):
#         value = extraction.get(key, default)

#         if value is None:
#             return default

#         if isinstance(value, str) and value.strip().lower() in {
#             "",
#             "not mentioned",
#             "not specified",
#             "no information",
#         }:
#             return default

#         return value

#     qa = [
#         ("Control Location", "Not specified"),
#         ("Contact Method", "Guidance/advice visit"),
#         ("Number of Customers", "1"),
#         ("Date & Time", metadata.get("date_time", "Not specified")),
#         ("Gender", get_value("Gender")),
#         ("Age Group", get_value("Age_Group")),
#         ("Reason for Immigration", get_value("Reason_for_Immigration")),
#         ("Labor Market Position", get_value("Labor_Market_Position")),
#         ("Customer's Domicile", get_value("Customers_Domicile")),
#         (
#             "Duration of Residence in Finland",
#             get_value("Duration_of_Residence_in_Finland"),
#         ),
#         ("Topics", get_value("Topics_Discussed")),
#         ("Country of Birth", get_value("Country_of_Birth")),
#         ("Mother Tongue", get_value("Mother_Tongue")),
#         ("Education Level", get_value("Education_Level")),
#         (
#             "Additional Notes",
#             (
#                 f"Services sought: {get_value('Services_Sought')}. "
#                 f"Guidance provided: {get_value('Guidance_Provided')}. "
#                 f"Referrals made: {get_value('Referrals_Made')}."
#             ),
#         ),
#     ]

#     df = pd.DataFrame(qa, columns=["Question", "Answer"])

#     output_dir = Path(output_dir)
#     output_dir.mkdir(parents=True, exist_ok=True)

#     stem = Path(OUTPUT_JSON_PATH).stem

#     csv_path = output_dir / f"{stem}_qa.csv"

#     df.to_csv(csv_path, index=False)

#     print(f"✅ CSV saved: {csv_path}")

#     return csv_path



# #print(f"\n💾  Saved: {OUTPUT_JSON_PATH}")
# print(f"\n💾 Saved JSON: {OUTPUT_JSON_PATH}")

# csv_path = json_to_qa_table(
#     final_output,
#     os.path.dirname(OUTPUT_JSON_PATH)
# )

# print(f"💾 Saved CSV : {csv_path}")


# print(f"    Size  : {os.path.getsize(OUTPUT_JSON_PATH):,} bytes")

# # Verify it round-trips cleanly
# with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
#     check = json.load(f)
# assert "metadata"   in check
# assert "summary"    in check
# assert "extraction" in check
# assert "transcript" in check
# print("    ✅  JSON integrity verified (all four sections present)")


# # ──────────────────────────────────────────────────────────────────────────
# # CELL 9 · Download from Colab
# # ──────────────────────────────────────────────────────────────────────────

# try:
#     from google.colab import files
#     print("\n📥  Downloading visit_log.json...")
#     files.download(OUTPUT_JSON_PATH)
#     print("✅  Download triggered.")
# except ImportError:
#     print(f"\nℹ️  Not running in Colab.")
#     print(f"    Output file: {OUTPUT_JSON_PATH}")

# print("\n" + "═"*70)
# print("  ✅  PIPELINE COMPLETE")
# print(f"     Sections in output JSON: metadata | summary | extraction | transcript")
# print("═"*70)

















# ──────────────────────────────────────────────────────────────────────────
# CELL 1 · Environment check (unchanged)
# ──────────────────────────────────────────────────────────────────────────
print("✅  Packages ready.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 2 · ⚙️  CONFIGURATION  ← only edit this cell
# ──────────────────────────────────────────────────────────────────────────

# HuggingFace token — https://huggingface.co/settings/tokens
# Accept the LLaMA licence at:  https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
HF_API_KEY = "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"

# Folder containing your audio files.
# Supported formats: .wav .mp3 .m4a .ogg .flac
INPUT_FOLDER_PATH = "/content/sample_data/Audios"     # ← CHANGE THIS TO YOUR FOLDER

# Output folder (will be created automatically)
OUTPUT_FOLDER = "data"

LLAMA_MODEL  = "meta-llama/Llama-3.1-8B-Instruct"
WHISPER_SIZE = "large-v3"

print("✅  Config loaded.")
print(f"    Model   : {LLAMA_MODEL}")
print(f"    Whisper : {WHISPER_SIZE}")
print(f"    Input folder : {INPUT_FOLDER_PATH}")
print(f"    Output folder: {OUTPUT_FOLDER}")


# ──────────────────────────────────────────────────────────────────────────
# CELL 3 · Imports
# ──────────────────────────────────────────────────────────────────────────

import os, re, json, torch
from datetime import datetime
from huggingface_hub import InferenceClient
import pandas as pd
from pathlib import Path
print("✅  Imports done.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 4 · Transcribe with Whisper
# ──────────────────────────────────────────────────────────────────────────

def transcribe(audio_path: str, model_size: str = "large-v3") -> tuple:
    """
    Transcribe audio with faster-whisper.
    Returns (full_text: str, segments: list[dict], whisper_meta: dict)

    Each segment dict:  { "start": float, "end": float, "text": str }
    """
    from faster_whisper import WhisperModel

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    device  = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    print(f"  Device  : {device}  ({compute})")
    print(f"  Loading : Whisper {model_size}")

    wmodel = WhisperModel(model_size, device=device, compute_type=compute)

    gen, info = wmodel.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        language=None,   # auto-detect
    )

    segments, texts = [], []
    for seg in gen:
        texts.append(seg.text)
        segments.append({
            "start": round(seg.start, 2),
            "end":   round(seg.end, 2),
            "text":  seg.text.strip(),
        })

    full_text = " ".join(texts).strip()
    full_text = re.sub(r"\s+", " ", full_text)                   # collapse spaces
    full_text = re.sub(r"(\w)\s*-\s*(\w)", r"\1\2", full_text)  # fix split-word ASR artefacts

    duration_sec = round(segments[-1]["end"] if segments else 0, 1)
    whisper_meta = {
        "language":             info.language,
        "language_probability": round(info.language_probability, 3),
        "duration_sec":         duration_sec,
        "segment_count":        len(segments),
        "char_count":           len(full_text),
    }

    print(f"  Language: {info.language}  (p={info.language_probability:.2f})")
    print(f"  Duration: {duration_sec}s  |  {len(segments)} segments  |  {len(full_text)} chars")
    return full_text, segments, whisper_meta


# ──────────────────────────────────────────────────────────────────────────
# CELL 5 · LLaMA helper — one reusable function for all LLM calls
# ──────────────────────────────────────────────────────────────────────────

def call_llama(
    system_prompt : str,
    user_prompt   : str,
    hf_api_key    : str,
    model         : str   = "meta-llama/Llama-3.1-8B-Instruct",
    max_tokens    : int   = 2048,
    temperature   : float = 0.15,
) -> str:
    """
    Single reusable wrapper for every LLaMA call in this notebook.
    Returns the raw string content from the model.
    Raises clearly on auth or connection errors.
    """
    if not hf_api_key or hf_api_key.startswith("hf_YOUR"):
        raise ValueError(
            "❌  HF_API_KEY is not set.\n"
            "    Get a token at https://huggingface.co/settings/tokens\n"
            "    and paste it into HF_API_KEY in Cell 2."
        )

    client = InferenceClient(token=hf_api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=0.9,
    )

    return response.choices[0].message.content.strip()


def parse_json_from_llm(raw: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response.
    Handles stray markdown fences and leading/trailing text.
    """
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    # Find the outermost { ... } block
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not json_match:
        return {"_error": "No JSON object found", "_raw": raw}

    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        return {"_error": str(e), "_raw": raw}


print("✅  LLaMA helper ready.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 6 · Step 1 — Detailed summary (prompt unchanged)
# ──────────────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM = """\
You are an expert case-notes writer for a Finnish immigrant guidance and integration service.
You write clear, accurate, and detailed summaries of customer visits based on
speech-recognition transcripts.

The transcript may be noisy (ASR errors, disfluencies, incomplete sentences).
Read for meaning, not literal wording.
Write in professional English. Be specific — include names, ages, places, services,
and decisions mentioned. Do not invent anything not in the transcript."""

SUMMARY_USER = """\
Below is the full speech-recognition transcript of a customer visit.

<transcript>
{transcript}
</transcript>

Write a detailed summary of this visit with the following six sections.
Use plain prose under each heading — no bullet points inside sections.

## 1. Customer Profile
Who is the customer? Include gender, approximate age or family situation,
country of origin or background, language skills, and how long they have
been in Finland — based only on what is mentioned in the transcript.

## 2. Reason for Visit
Why did the customer come to the service today?
What specific question or problem brought them in?

## 3. Topics Discussed
What topics and subjects came up during the conversation?
Describe each topic in a sentence or two, covering what the customer asked
and what angle the conversation took.

## 4. Guidance and Information Provided
What information, advice, or guidance was given to the customer?
Be specific: mention services named, steps explained, documents referred to,
websites or phone numbers mentioned, eligibility conditions discussed, etc.

## 5. Referrals and Next Steps
What services or organisations was the customer referred to?
What actions does the customer need to take next?
What follow-up is expected?

## 6. Additional Observations
Note anything else relevant: customer's emotional state if apparent,
communication challenges, outstanding questions not fully resolved,
or anything unusual about the visit."""


def generate_summary(transcript: str) -> str:
    print("  Sending summary prompt...")
    raw = call_llama(
        system_prompt = SUMMARY_SYSTEM,
        user_prompt   = SUMMARY_USER.format(transcript=transcript),
        hf_api_key    = HF_API_KEY,
        model         = LLAMA_MODEL,
        max_tokens    = 1500,
        temperature   = 0.20,
    )
    print(f"  ✅  Summary received ({len(raw)} chars)")
    return raw


# ──────────────────────────────────────────────────────────────────────────
# CELL 7 · Step 2 — Structured field extraction (prompt unchanged)
# ──────────────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM = """\
You are a structured data extraction assistant for a Finnish immigrant guidance service.
Extract specific fields from a noisy speech-recognition transcript of a customer visit.

Rules:
- Interpret semantic meaning, not literal wording. Transcripts are noisy.
- If a field is NOT present in the transcript: write "No information" (categorical)
  or "Not specified" (free text). Never guess or invent.
- Pronoun rule: she / her / mother → Gender = Woman.  he / his / father → Gender = Man.
- Topics: list ALL explicitly discussed topics, separated by semicolons.
- Return ONLY a valid JSON object. No markdown. No code fences. No extra text."""


def build_extraction_prompt(transcript: str, duration_sec: float) -> str:
    mins = int(duration_sec // 60)
    secs = int(duration_sec % 60)
    duration_label = f"{mins} min {secs} sec" if mins > 0 else f"{secs} sec"

    return f"""\
Transcript of a customer visit to an immigrant guidance service:

<transcript>
{transcript}
</transcript>

Fill in every field in the JSON template below.
Use only the options shown in angle brackets, or write "No information" / "Not specified".

{{
  "Gender":
    "<Woman | Man | Non-binary | No information>",

  "Age_Group":
    "<Child 0-12 | Teenager 13-17 | Young adult 18-29 | Adult 30-64 | Senior 65+ | No information>
     If customer has a child, append child age: e.g. 'Adult 30-64 (parent of 3-year-old)'",

  "Reason_for_Immigration":
    "<Work | Family reunification | Refugee / Asylum seeker | Student | Other | No information>",

  "Labor_Market_Position":
    "<Working in the open market | Unemployed job seeker | Student | On parental leave | Retired | No information>",

  "Customers_Domicile":
    "<Finnish city name, or 'Not specified'>",

  "Duration_of_Residence_in_Finland":
    "<Less than 3 months | Less than 1 year | 1-3 years | 3-5 years | More than 5 years | No information>",

  "Country_of_Birth":
    "<country name, or 'Not specified'>",

  "Mother_Tongue":
    "<language name(s), or 'Not specified'>",

  "Finnish_Language_Skills":
    "<None | Basic | Conversational | Fluent | Not mentioned>",

  "Education_Level":
    "<Primary / basic | Secondary | Vocational | University / higher | No information>",

  "Topics_Discussed":
    "<semicolon-separated topics — e.g. 'Early childhood education; Kela benefits; Residence permit'>",

  "Number_of_People_in_Household":
    "<integer, or 'Not specified'>",

  "How_Customer_Heard_About_Service":
    "<word of mouth | online search | referral from another service | signage | not mentioned>",

  "Services_Sought":
    "<what the customer was specifically looking for — 1-2 sentences>",

  "Guidance_Provided":
    "<what guidance or information was given — 1-2 sentences>",

  "Referrals_Made":
    "<organisations or services the customer was referred to, or 'None mentioned'>",

  "Confidence_Notes":
    "<fields you are uncertain about and why, or 'All fields extracted with reasonable confidence'>"
}}

Estimated visit duration from audio: {duration_label}
Date: {datetime.now().strftime("%d/%m/%Y")}"""


def extract_fields(transcript: str, duration_sec: float) -> dict:
    print("  Sending extraction prompt...")
    raw = call_llama(
        system_prompt = EXTRACTION_SYSTEM,
        user_prompt   = build_extraction_prompt(transcript, duration_sec),
        hf_api_key    = HF_API_KEY,
        model         = LLAMA_MODEL,
        max_tokens    = 1200,
        temperature   = 0.05,
    )
    print(f"  Raw response: {len(raw)} chars")
    parsed = parse_json_from_llm(raw)

    if "_error" in parsed:
        print(f"  ⚠️  JSON parse failed: {parsed['_error']}")
        print("  Raw LLM output saved in _raw field.")
    else:
        print(f"  ✅  Parsed — {len(parsed)} fields extracted")

    return parsed


# ──────────────────────────────────────────────────────────────────────────
# CELL 8 · Assemble final output & save (modified to accept file-specific paths)
# ──────────────────────────────────────────────────────────────────────────

def assemble_output(
    transcript   : str,
    segments     : list,
    whisper_meta : dict,
    summary_text : str,
    extraction   : dict,
    audio_path   : str,
) -> dict:
    """
    Assemble all pipeline outputs into a single clean JSON-serialisable dict.
    """
    mins = int(whisper_meta["duration_sec"] // 60)
    secs = int(whisper_meta["duration_sec"]  % 60)

    return {
        "metadata": {
            "date_time":            datetime.now().strftime("%d/%m/%Y %H:%M"),
            "visit_duration":       f"{mins} min {secs} sec",
            "audio_file":           os.path.basename(audio_path),
            "whisper_model":        WHISPER_SIZE,
            "llm_model":            LLAMA_MODEL,
            "detected_language":    whisper_meta["language"],
            "language_probability": whisper_meta["language_probability"],
            "audio_duration_sec":   whisper_meta["duration_sec"],
            "transcript_char_count": whisper_meta["char_count"],
            "segment_count":        whisper_meta["segment_count"],
        },

        "summary": summary_text,

        "extraction": extraction,

        "transcript": {
            "full_text": transcript,
            "segments":  segments,
        },
    }


def json_to_qa_table(data: dict, output_json_path: str) -> Path:
    """
    Convert extraction output into QA CSV, saved next to the JSON file.
    """
    metadata = data.get("metadata", {})
    extraction = data.get("extraction", {})

    def get_value(key, default="Not specified"):
        value = extraction.get(key, default)
        if value is None:
            return default
        if isinstance(value, str) and value.strip().lower() in {
            "", "not mentioned", "not specified", "no information"
        }:
            return default
        return value

    qa = [
        ("Control Location", "Not specified"),
        ("Contact Method", "Guidance/advice visit"),
        ("Number of Customers", "1"),
        ("Date & Time", metadata.get("date_time", "Not specified")),
        ("Gender", get_value("Gender")),
        ("Age Group", get_value("Age_Group")),
        ("Reason for Immigration", get_value("Reason_for_Immigration")),
        ("Labor Market Position", get_value("Labor_Market_Position")),
        ("Customer's Domicile", get_value("Customers_Domicile")),
        ("Duration of Residence in Finland", get_value("Duration_of_Residence_in_Finland")),
        ("Topics", get_value("Topics_Discussed")),
        ("Country of Birth", get_value("Country_of_Birth")),
        ("Mother Tongue", get_value("Mother_Tongue")),
        ("Education Level", get_value("Education_Level")),
        ("Additional Notes", (
            f"Services sought: {get_value('Services_Sought')}. "
            f"Guidance provided: {get_value('Guidance_Provided')}. "
            f"Referrals made: {get_value('Referrals_Made')}."
        )),
    ]

    df = pd.DataFrame(qa, columns=["Question", "Answer"])
    csv_path = Path(output_json_path).with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    print(f"  ✅ CSV saved: {csv_path}")
    return csv_path


def process_one_audio(audio_path: str, output_folder: str) -> dict:
    """
    Run the full pipeline on a single audio file.
    Returns the final output dict, or None on failure.
    """
    print(f"\n{'='*70}")
    print(f"🎧 Processing: {os.path.basename(audio_path)}")
    print('='*70)

    try:
        # 1. Transcribe
        print("🎙️  Transcribing...")
        transcript, segments, whisper_meta = transcribe(audio_path, WHISPER_SIZE)
        print(f"📝  Transcript preview (first 300 chars):\n{transcript[:300]}...")

        # 2. Generate summary
        print("\n📝  Generating detailed summary...")
        summary_text = generate_summary(transcript)

        # 3. Extract structured fields
        print("\n🔍  Extracting structured fields...")
        extraction = extract_fields(transcript, whisper_meta["duration_sec"])

        # 4. Assemble final output
        final_output = assemble_output(
            transcript=transcript,
            segments=segments,
            whisper_meta=whisper_meta,
            summary_text=summary_text,
            extraction=extraction,
            audio_path=audio_path,
        )

        # 5. Save JSON
        stem = Path(audio_path).stem
        output_json_path = Path(output_folder) / f"{stem}_analysis.json"
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved JSON: {output_json_path}")

        # 6. Save QA CSV
        json_to_qa_table(final_output, output_json_path)

        # 7. Verification
        with open(output_json_path, "r", encoding="utf-8") as f:
            check = json.load(f)
        assert "metadata" in check and "summary" in check and "extraction" in check and "transcript" in check
        print("    ✅ JSON integrity verified")

        return final_output

    except Exception as e:
        print(f"\n❌ ERROR processing {audio_path}: {str(e)}")
        return None


# ──────────────────────────────────────────────────────────────────────────
# CELL 9 · Main loop over all audio files in the input folder
# ──────────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg", ".flac")

def get_audio_files(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Input folder does not exist: {folder_path}")
    return [f for f in folder.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]

# Create output folder
output_path = Path(OUTPUT_FOLDER)
output_path.mkdir(parents=True, exist_ok=True)
print(f"📁 Output folder ready: {output_path.absolute()}")

audio_files = get_audio_files(INPUT_FOLDER_PATH)
print(f"\n🎵 Found {len(audio_files)} audio file(s) in {INPUT_FOLDER_PATH}:")
for f in audio_files:
    print(f"  - {f.name}")

# Process each file
results = {}
for audio_file in audio_files:
    result = process_one_audio(str(audio_file), OUTPUT_FOLDER)
    results[audio_file.name] = "✅ success" if result is not None else "❌ failed"

# Summary
print("\n" + "═"*70)
print("  📊 PROCESSING SUMMARY")
print("═"*70)
for name, status in results.items():
    print(f"  {status}  {name}")
print("═"*70)
print(f"✅ All done. Results saved in '{OUTPUT_FOLDER}'")