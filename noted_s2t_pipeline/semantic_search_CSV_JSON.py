# ──────────────────────────────────────────────────────────────────────────
# CELL 1 · Environment check (unchanged)
# ──────────────────────────────────────────────────────────────────────────
print("✅ Packages ready.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 2 · ⚙️ CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────

HF_API_KEY = "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"

INPUT_FOLDER_PATH = "/content/sample_data/Audios"
OUTPUT_FOLDER = "data"

LLAMA_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
WHISPER_SIZE = "large-v3"

# New: Embedding settings
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # Good for Finnish + English

# EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"


print("✅ Config loaded.")
print(f"    LLM     : {LLAMA_MODEL}")
print(f"    Whisper : {WHISPER_SIZE}")
print(f"    Embedding: {EMBEDDING_MODEL}")
print(f"    Input   : {INPUT_FOLDER_PATH}")


# ──────────────────────────────────────────────────────────────────────────
# CELL 3 · Imports
# ──────────────────────────────────────────────────────────────────────────

import os, re, json, torch
from datetime import datetime
from huggingface_hub import InferenceClient
import pandas as pd
from pathlib import Path

# New imports for embeddings + semantic search
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

print("✅ Imports done.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 4 · Transcribe with Whisper (unchanged)
# ──────────────────────────────────────────────────────────────────────────
def transcribe(audio_path: str, model_size: str = "large-v3") -> tuple:
    from faster_whisper import WhisperModel

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    print(f"  Device: {device} ({compute})")

    wmodel = WhisperModel(model_size, device=device, compute_type=compute)

    gen, info = wmodel.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        language=None,
    )

    segments, texts = [], []
    for seg in gen:
        texts.append(seg.text)
        segments.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })

    full_text = " ".join(texts).strip()
    full_text = re.sub(r"\s+", " ", full_text)
    full_text = re.sub(r"(\w)\s*-\s*(\w)", r"\1\2", full_text)

    duration_sec = round(segments[-1]["end"] if segments else 0, 1)
    whisper_meta = {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration_sec": duration_sec,
        "segment_count": len(segments),
        "char_count": len(full_text),
    }

    print(f"  Language: {info.language} | Duration: {duration_sec}s | {len(segments)} segments")
    return full_text, segments, whisper_meta


# ──────────────────────────────────────────────────────────────────────────
# CELL 5 · LLaMA helper + JSON parser (unchanged)
# ──────────────────────────────────────────────────────────────────────────
def call_llama(system_prompt: str, user_prompt: str, hf_api_key: str, model=LLAMA_MODEL,
               max_tokens=2048, temperature=0.15) -> str:
    if not hf_api_key or hf_api_key.startswith("hf_YOUR"):
        raise ValueError("❌ HF_API_KEY not set.")

    client = InferenceClient(token=hf_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=0.9,
    )
    return response.choices[0].message.content.strip()


def parse_json_from_llm(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not json_match:
        return {"_error": "No JSON object found", "_raw": raw}
    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        return {"_error": str(e), "_raw": raw}


print("✅ LLaMA helper ready.")





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
# NEW: CELL 7.5 · Embeddings + Semantic Search Helpers
# ──────────────────────────────────────────────────────────────────────────

def build_semantic_index(segments: list) -> tuple:
    """Build FAISS index from transcript segments"""
    print("  Building semantic index...")

    embedder = SentenceTransformer(EMBEDDING_MODEL)

    # Use segments as natural chunks (already timed and coherent)
    texts = [seg["text"] for seg in segments]
    embeddings = embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)        # Inner Product = cosine similarity when normalized
    index.add(embeddings)

    return index, texts, embedder



# USE THIS FOR QWEN MODEL
# def build_semantic_index(segments: list) -> tuple:
#     """Build FAISS index from transcript segments"""
#     print(f"  Building semantic index with {EMBEDDING_MODEL}...")

#     embedder = SentenceTransformer(
#         EMBEDDING_MODEL,
#         model_kwargs={"trust_remote_code": True}   # Important for Qwen models
#     )

#     # Use segments as natural chunks
#     texts = [seg["text"] for seg in segments if seg["text"].strip()]

#     print(f"  Encoding {len(texts)} segments...")
#     embeddings = embedder.encode(
#         texts,
#         convert_to_numpy=True,
#         normalize_embeddings=True,
#         batch_size=32,                    # Good for larger models
#         show_progress_bar=True
#     )

#     dimension = embeddings.shape[1]
#     index = faiss.IndexFlatIP(dimension)
#     index.add(embeddings)

#     print(f"  ✅ Index built with dimension {dimension}")
#     return index, texts, embedder




def semantic_search(query: str, index, texts, embedder, top_k: int = 6):
    """Retrieve most relevant chunks for a question"""
    query_emb = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    scores, indices = index.search(query_emb, top_k)

    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(texts):
            results.append({
                "text": texts[idx],
                "score": float(score)
            })
    return results


def answer_with_context(question: str, relevant_chunks: list) -> str:
    """Ask LLM with only relevant context"""
    context = "\n\n".join([f"• {chunk['text']}" for chunk in relevant_chunks])

    system = "You are a precise assistant extracting information from a customer service transcript."
    user = f"""\
Context (most relevant parts of the conversation):
{context}

Question: {question}

Answer concisely based only on the context above. If not mentioned, say "Not specified"."""

    return call_llama(system, user, HF_API_KEY, max_tokens=400, temperature=0.0)


print("✅ Semantic search helpers ready.")


# ──────────────────────────────────────────────────────────────────────────
# CELL 8 · Assemble + Save (JSON unchanged)
# ──────────────────────────────────────────────────────────────────────────
def assemble_output(transcript, segments, whisper_meta, summary_text, extraction, audio_path):
    # (Exactly the same as your original function)
    mins = int(whisper_meta["duration_sec"] // 60)
    secs = int(whisper_meta["duration_sec"] % 60)

    return {
        "metadata": {
            "date_time": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "visit_duration": f"{mins} min {secs} sec",
            "audio_file": os.path.basename(audio_path),
            "whisper_model": WHISPER_SIZE,
            "llm_model": LLAMA_MODEL,
            "detected_language": whisper_meta["language"],
            "language_probability": whisper_meta["language_probability"],
            "audio_duration_sec": whisper_meta["duration_sec"],
            "transcript_char_count": whisper_meta["char_count"],
            "segment_count": whisper_meta["segment_count"],
        },
        "summary": summary_text,
        "extraction": extraction,
        "transcript": {"full_text": transcript, "segments": segments},
    }


def semantic_json_to_qa_table(data: dict, output_json_path: str) -> Path:
    """NEW: Better CSV using semantic search"""
    metadata = data.get("metadata", {})
    transcript_segments = data["transcript"]["segments"]

    index, texts, embedder = build_semantic_index(transcript_segments)

    qa_pairs = [
        ("Control Location", "Not specified"),
        ("Contact Method", "Guidance/advice visit"),
        ("Number of Customers", "1"),
        ("Date & Time", metadata.get("date_time", "Not specified")),
    ]

    questions = {
        "Gender": "What is the gender of the customer?",
        "Age Group": "What is the age group of the customer? Include any mention of children.",
        "Reason for Immigration": "What was the reason for immigration?",
        "Labor Market Position": "What is the customer's labor market position?",
        "Customer's Domicile": "Where does the customer live (city)?",
        "Duration of Residence in Finland": "How long has the customer lived in Finland?",
        "Country of Birth": "What is the customer's country of birth?",
        "Mother Tongue": "What is the customer's mother tongue?",
        "Education Level": "What is the customer's education level?",
        "Topics": "What topics were discussed in this visit?",
    }

    for q_label, q_text in questions.items():
        relevant = semantic_search(q_text, index, texts, embedder, top_k=5)
        answer = answer_with_context(q_text, relevant)
        qa_pairs.append((q_label, answer))

    # Additional notes from structured extraction (fallback + enrichment)
    extraction = data.get("extraction", {})
    additional = (
        f"Services sought: {extraction.get('Services_Sought', 'Not specified')}. "
        f"Guidance: {extraction.get('Guidance_Provided', 'Not specified')}. "
        f"Referrals: {extraction.get('Referrals_Made', 'None mentioned')}."
    )
    qa_pairs.append(("Additional Notes", additional))

    df = pd.DataFrame(qa_pairs, columns=["Question", "Answer"])
    csv_path = Path(output_json_path).with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    print(f"  ✅ Semantic CSV saved: {csv_path}")
    return csv_path


# ──────────────────────────────────────────────────────────────────────────
# CELL 9 · Processing pipeline
# ──────────────────────────────────────────────────────────────────────────
def process_one_audio(audio_path: str, output_folder: str):
    print(f"\n{'='*70}")
    print(f"🎧 Processing: {os.path.basename(audio_path)}")
    print('='*70)

    try:
        # 1. Transcribe
        transcript, segments, whisper_meta = transcribe(audio_path, WHISPER_SIZE)

        # 2. Summary
        summary_text = generate_summary(transcript)

        # 3. Structured extraction (for JSON)
        extraction = extract_fields(transcript, whisper_meta["duration_sec"])

        # 4. Assemble JSON (unchanged)
        final_output = assemble_output(transcript, segments, whisper_meta, summary_text, extraction, audio_path)

        # 5. Save JSON
        stem = Path(audio_path).stem
        output_json_path = Path(output_folder) / f"{stem}_analysis.json"
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved JSON: {output_json_path}")

        # 6. NEW Semantic CSV
        semantic_json_to_qa_table(final_output, output_json_path)

        print("    ✅ Processing completed successfully")
        return final_output

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return None


# ──────────────────────────────────────────────────────────────────────────
# CELL 10 · Main loop
# ──────────────────────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg", ".flac")

def get_audio_files(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Input folder not found: {folder_path}")
    return [f for f in folder.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS]

output_path = Path(OUTPUT_FOLDER)
output_path.mkdir(parents=True, exist_ok=True)

audio_files = get_audio_files(INPUT_FOLDER_PATH)
print(f"Found {len(audio_files)} audio file(s)")

results = {}
for audio_file in audio_files:
    result = process_one_audio(str(audio_file), OUTPUT_FOLDER)
    results[audio_file.name] = "✅ success" if result else "❌ failed"

print("\n" + "═"*70)
print("PROCESSING SUMMARY")
print("═"*70)
for name, status in results.items():
    print(f"{status}  {name}")
print("═"*70)
print(f"✅ All done. JSONs and improved CSVs saved in '{OUTPUT_FOLDER}'")