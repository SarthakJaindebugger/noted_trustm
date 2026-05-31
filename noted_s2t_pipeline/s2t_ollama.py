
from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =========================
# USER CONFIGURATION
# =========================
AUDIO_PATH = r"/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/Lucy_audio_dialoges/dia02sce2MC.WAV"
OUTPUT_DIR = "/Users/sarthakjain/Desktop/ML Projects/noted-main/noted_s2t_pipeline/outputs/"
WHISPER_MODEL        = "base"
WHISPER_DEVICE       = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
OLLAMA_MODEL         = "llama3.2"
USE_OLLAMA_IF_AVAILABLE = True
DEBUG_LLM_RESPONSES  = True   # prints raw LLM output per question for debugging


# =========================
# FORM SPEC
# =========================
FORM_QUESTIONS: List[Dict[str, Any]] = [
    {"key": "control_location",       "question": "Control Location"},
    {"key": "visit_datetime",         "question": "Date & Time"},
    {"key": "visit_duration",         "question": "Visit Duration"},
    {"key": "contact_method",         "question": "Contact Method"},
    {"key": "heard_from",             "question": "Heard From"},
    {"key": "where_if_other",         "question": "If Other, WHERE?"},
    {"key": "number_of_customers",    "question": "Number of Customers"},
    {"key": "gender",                 "question": "Gender"},
    {"key": "age_group",              "question": "Age Group"},
    {"key": "reason_for_immigration", "question": "Reason for Immigration"},
    {"key": "additional_info",        "question": "Additional Info"},
    {"key": "country_of_birth",       "question": "Country of Birth"},
    {"key": "mother_tongue",          "question": "Mother Tongue"},
    {"key": "education_level",        "question": "Education Level"},
    {"key": "labor_market_position",  "question": "Labor Market Position"},
    {"key": "customer_domicile",      "question": "Customer's Domicile"},
    {"key": "residence_in_finland",   "question": "Duration of Residence in Finland"},
    {"key": "topics_of_discussion",   "question": "Topic of Discussion"},
    {"key": "purpose_of_visit",       "question": "Purpose of Visit"},
    {"key": "additional_notes",       "question": "Additional Information Notes"},
    {"key": "referrals",              "question": "Where the Customer is Directed / Referred"},
    {"key": "other_feedback",         "question": "Other Feedback"},
]


# =========================
# VALID ENUM OPTIONS
# =========================
VALID_CONTACT_METHODS = [
    "Visit to a guidance/advice point",
    "Telephone conversation (call, WhatsApp)",
    "Written contact (e.g. email, WhatsApp chat, social media)",
    "Remote connection (e.g. Teams, Zoom)",
    "Electronic service (e.g. online form)",
    "Field work",
]
VALID_GENDER     = ["Man", "Woman", "No information"]
VALID_AGE_GROUPS = ["Under 18", "18-25", "26-35", "36-50", "50+", "No information"]
VALID_LABOR      = [
    "No information", "Working in the open market", "Working outside the open market",
    "Entrepreneur", "Unemployed", "In labor policy training", "Student",
    "Outside the labor market", "Planning to move to Finland",
]
VALID_RESIDENCE  = [
    "No information", "Does not live in Finland",
    "Less than 3 years", "3-5 years", "More than 5 years",
]
VALID_TOPICS     = [
    "Residence", "Benefits (e.g. Kela)", "Hobbies and leisure",
    "Matters related to education", "Crisis situations", "Immigration process",
    "Legal matters", "Family life", "Police matters", "Social affairs",
    "Studying Finnish/Swedish", "Finance", "Health care",
    "Working conditions / occupational health & safety", "Work", "Career guidance",
]
VALID_PURPOSES   = [
    "Initial interview", "Digital help", "Language support", "Filling out forms",
    "Clarifying decisions and processes", "Group info",
    "Contacting an authority or another entity", "Other guidance and support",
]
VALID_REFERRALS  = [
    "Trade unions / occupational safety", "Lawyer and legal aid services",
    "Real estate / housing agency", "Digital and Population Information Agency",
    "Human trafficking help system", "Organizations and associations", "Traficom",
    "School activity", "Crisis services", "Municipal immigrant & integration services",
    "Finnish Immigration Service (Migri)", "Youth services", "Educational institution",
    "Police", "Congregations / religious communities", "Social and family services",
    "Embassy", "TE services", "Health services", "Kela", "Early childhood education",
    "Tax office", "Shared service point", "Support services for entrepreneurs",
    "Companies / employers", "Other entities", "Case closed",
    "Customer service continues / Make a new appointment",
    "Guidance and counseling service in another location",
]


# =========================
# PER-QUESTION PROMPTS
# Each entry:  system_prompt, user_template  (use {fact_sheet} placeholder)
# =========================
QUESTION_PROMPTS: Dict[str, Dict[str, str]] = {

    "control_location": {
        "system": "You extract the exact service office or location name from a fact sheet. Return the name only. No explanation.",
        "user": """From the fact sheet below, what is the name of the service office or location where this visit took place?
Return ONLY the location name. If not found return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "visit_datetime": {
        "system": "You extract date and time information from a fact sheet. Return in DD/MM/YYYY HH:MM format if possible.",
        "user": """From the fact sheet below, what was the date and time of the visit?
Return ONLY the date/time, e.g. 08/04/2025 08:21. If not found return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    # visit_duration is computed deterministically — no prompt needed
    "visit_duration": {"system": "", "user": ""},

    "contact_method": {
        "system": "You classify how a customer contacted a service. Return EXACTLY one option from the list provided.",
        "user": """From the fact sheet below, how did the customer make contact with the service?
Return EXACTLY one of these options (copy it verbatim):
- Visit to a guidance/advice point
- Telephone conversation (call, WhatsApp)
- Written contact (e.g. email, WhatsApp chat, social media)
- Remote connection (e.g. Teams, Zoom)
- Electronic service (e.g. online form)
- Field work

If not clear, return: Visit to a guidance/advice point
Return ONLY the option text, nothing else.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "heard_from": {
        "system": "You extract short phrases from fact sheets. Be concise.",
        "user": """From the fact sheet below, how did the customer hear about this service?
Return a short phrase (e.g. 'a friend', 'social media', 'flyer', 'Kela office').
If not mentioned return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "where_if_other": {
        "system": "You extract location details from fact sheets.",
        "user": """From the fact sheet below, if the contact method was field work or the customer was visited somewhere outside the office, what was that location?
If not applicable or not mentioned, return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "number_of_customers": {
        "system": "You extract integers from fact sheets.",
        "user": """From the fact sheet below, how many customers were served in this visit?
Return ONLY an integer. If not mentioned, return 1.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "gender": {
        "system": "You classify gender from a fact sheet. Return exactly one of the allowed values.",
        "user": """From the fact sheet below, what is the customer's gender?
Return EXACTLY one of: Man | Woman | No information

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "age_group": {
        "system": "You classify age groups from a fact sheet.",
        "user": """From the fact sheet below, what is the customer's age group?
If an exact age is mentioned, map it: under 18 → Under 18, 18-25 → 18-25, 26-35 → 26-35, 36-50 → 36-50, over 50 → 50+.
Return EXACTLY one of: Under 18 | 18-25 | 26-35 | 36-50 | 50+ | No information

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "reason_for_immigration": {
        "system": "You extract immigration reasons from fact sheets. Be brief.",
        "user": """From the fact sheet below, why did the customer immigrate to Finland?
Common reasons: Work, Family, Study, Refugee, Marriage, Asylum, Other.
Return a short phrase or empty string if not mentioned.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "additional_info": {
        "system": "You identify special circumstances from a fact sheet. Use only the allowed values.",
        "user": """From the fact sheet below, does the customer have any of these special circumstances?
- Illiterate
- Paperless (no official documents)
- Tourist
- Ukraine crisis (arrived due to Ukraine war)

Return only the matching items separated by semicolons.
If none apply, return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "country_of_birth": {
        "system": "You extract country names from fact sheets.",
        "user": """From the fact sheet below, what is the customer's country of birth or country of origin?
Return ONLY the country name. If not mentioned return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "mother_tongue": {
        "system": "You extract language names from fact sheets.",
        "user": """From the fact sheet below, what is the customer's mother tongue or native language?
Return ONLY the language name. If not mentioned return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "education_level": {
        "system": "You classify education levels from fact sheets.",
        "user": """From the fact sheet below, what is the customer's highest education level?
Return EXACTLY one of: Primary | High school | Vocational | Bachelor's | Master's | PhD | No information

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "labor_market_position": {
        "system": "You classify employment status from a fact sheet. Return exactly one allowed value.",
        "user": """From the fact sheet below, what is the customer's current employment or labor market status?
Return EXACTLY one of:
- No information
- Working in the open market
- Working outside the open market
- Entrepreneur
- Unemployed
- In labor policy training
- Student
- Outside the labor market
- Planning to move to Finland

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "customer_domicile": {
        "system": "You extract place names from fact sheets.",
        "user": """From the fact sheet below, what city or municipality does the customer currently live in (domicile)?
Return ONLY the place name. If not mentioned return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "residence_in_finland": {
        "system": "You classify duration of residence from a fact sheet. Return exactly one allowed value.",
        "user": """From the fact sheet below, how long has the customer been living in Finland?
Return EXACTLY one of:
- No information
- Does not live in Finland
- Less than 3 years
- 3-5 years
- More than 5 years

Map time mentions: "2 years" → Less than 3 years, "4 years" → 3-5 years, "7 years" → More than 5 years.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "topics_of_discussion": {
        "system": "You identify discussion topics from a fact sheet. Return only items from the allowed list, semicolon-separated.",
        "user": """From the fact sheet below, which of these topics were discussed during the visit?
Pick ALL that apply from this list:
- Residence
- Benefits (e.g. Kela)
- Hobbies and leisure
- Matters related to education
- Crisis situations
- Immigration process
- Legal matters
- Family life
- Police matters
- Social affairs
- Studying Finnish/Swedish
- Finance
- Health care
- Working conditions / occupational health & safety
- Work
- Career guidance

Return the matching topics separated by semicolons. If none match, return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "purpose_of_visit": {
        "system": "You identify the purpose of a service visit from a fact sheet. Return only items from the allowed list, semicolon-separated.",
        "user": """From the fact sheet below, what was the purpose of the customer's visit?
Pick ALL that apply from this list:
- Initial interview
- Digital help
- Language support
- Filling out forms
- Clarifying decisions and processes
- Group info
- Contacting an authority or another entity
- Other guidance and support

Return matching purposes separated by semicolons. If none match, return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "additional_notes": {
        "system": "You write brief visit summaries from fact sheets. Be concise and factual.",
        "user": """Based on the fact sheet below, write a 1-3 sentence factual summary of what happened during this customer visit.
Cover: why the customer came, what was discussed, and what the advisor did.

FACT SHEET:
{fact_sheet}

SUMMARY:""",
    },

    "referrals": {
        "system": "You identify referrals made during a service visit. Return only items from the allowed list, semicolon-separated.",
        "user": """From the fact sheet below, which organisations or services was the customer referred or directed to?
Pick ALL that apply from this list:
- Trade unions / occupational safety
- Lawyer and legal aid services
- Real estate / housing agency
- Digital and Population Information Agency
- Human trafficking help system
- Organizations and associations
- Traficom
- School activity
- Crisis services
- Municipal immigrant & integration services
- Finnish Immigration Service (Migri)
- Youth services
- Educational institution
- Police
- Congregations / religious communities
- Social and family services
- Embassy
- TE services
- Health services
- Kela
- Early childhood education
- Tax office
- Shared service point
- Support services for entrepreneurs
- Companies / employers
- Other entities
- Case closed
- Customer service continues / Make a new appointment
- Guidance and counseling service in another location

Return matching referrals separated by semicolons. If none match, return empty string.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },

    "other_feedback": {
        "system": "You extract feedback and remarks from fact sheets.",
        "user": """From the fact sheet below, is there any additional feedback, training needs mentioned, or remarks from the advisor?
Return a short summary or empty string if nothing extra was noted.

FACT SHEET:
{fact_sheet}

ANSWER:""",
    },
}


# =========================
# DATA CLASSES & UTILITIES
# =========================
@dataclass
class TranscriptSegment:
    speaker: str
    start:   float
    end:     float
    text:    str


def ensure_output_dir() -> Path:
    out_dir = Path(OUTPUT_DIR).expanduser().resolve() if OUTPUT_DIR else (
        Path(AUDIO_PATH).expanduser().resolve().parent /
        f"{Path(AUDIO_PATH).stem}_parsed_output"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def format_ts(seconds: float) -> str:
    """Convert float seconds to HH:MM:SS string."""
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def normalize_answer(answer: Any) -> str:
    if answer is None:
        return ""
    if isinstance(answer, bool):
        return "Yes" if answer else "No"
    if isinstance(answer, (int, float)):
        return str(answer)
    if isinstance(answer, list):
        return "; ".join(normalize_answer(x) for x in answer if str(x).strip())
    text = str(answer).strip().strip('"').strip("'")
    if text.lower() in ("not mentioned", "not provided", "unknown", "n/a", "none", "null", ""):
        return ""
    return text


def fuzzy_match_enum(value: str, valid_options: List[str]) -> str:
    if not value:
        return value
    v_low = value.lower().strip()
    for opt in valid_options:
        if opt.lower() == v_low:
            return opt
    for opt in valid_options:
        if v_low in opt.lower() or opt.lower() in v_low:
            return opt
    v_words = set(v_low.split())
    best_score, best_opt = 0, value
    for opt in valid_options:
        score = len(v_words & set(opt.lower().split()))
        if score > best_score:
            best_score, best_opt = score, opt
    return best_opt if best_score >= 2 else value


def normalise_multi(raw: str, valid_options: List[str]) -> str:
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"[;\n]", raw) if p.strip()]
    seen, mapped = set(), []
    for p in parts:
        m = fuzzy_match_enum(p, valid_options)
        if m and m not in seen:
            seen.add(m)
            mapped.append(m)
    return "; ".join(mapped)


def postprocess(results: Dict[str, str]) -> Dict[str, str]:
    r = dict(results)
    if r.get("contact_method"):
        r["contact_method"]        = fuzzy_match_enum(r["contact_method"], VALID_CONTACT_METHODS)
    if r.get("gender"):
        r["gender"]                = fuzzy_match_enum(r["gender"], VALID_GENDER)
    if r.get("age_group"):
        r["age_group"]             = fuzzy_match_enum(r["age_group"], VALID_AGE_GROUPS)
    if r.get("labor_market_position"):
        r["labor_market_position"] = fuzzy_match_enum(r["labor_market_position"], VALID_LABOR)
    if r.get("residence_in_finland"):
        r["residence_in_finland"]  = fuzzy_match_enum(r["residence_in_finland"], VALID_RESIDENCE)
    r["topics_of_discussion"]      = normalise_multi(r.get("topics_of_discussion", ""), VALID_TOPICS)
    r["purpose_of_visit"]          = normalise_multi(r.get("purpose_of_visit", ""), VALID_PURPOSES)
    r["referrals"]                 = normalise_multi(r.get("referrals", ""), VALID_REFERRALS)
    return r


# =========================
# TIMESTAMP UTILITIES
# =========================
def get_audio_timestamps(transcript_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract first and last timestamps directly from Whisper segments.
    Duration = last_segment.end - first_segment.start  (exact audio time).
    """
    segments = transcript_data.get("segments", [])
    if not segments:
        return {
            "conversation_start_seconds": None,
            "conversation_end_seconds":   None,
            "conversation_start_ts":      None,
            "conversation_end_ts":        None,
            "duration_seconds":           None,
            "duration_minutes":           None,
            "duration_formatted":         None,
        }

    start_sec = float(segments[0]["start"])
    end_sec   = float(segments[-1]["end"])
    dur_sec   = max(0.0, end_sec - start_sec)
    dur_min   = round(dur_sec / 60, 2)

    return {
        "conversation_start_seconds": round(start_sec, 3),
        "conversation_end_seconds":   round(end_sec, 3),
        "conversation_start_ts":      format_ts(start_sec),
        "conversation_end_ts":        format_ts(end_sec),
        "duration_seconds":           round(dur_sec, 3),
        "duration_minutes":           dur_min,
        "duration_formatted":         f"{int(dur_min)} min {int(dur_sec % 60)} sec",
    }


# =========================
# TRANSCRIPTION
# =========================
def transcribe_audio(audio_path: Path) -> Dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("pip install faster-whisper") from exc

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments_iter, info = model.transcribe(
        str(audio_path), beam_size=1, vad_filter=True,
        word_timestamps=False, multilingual=True,
    )

    raw: List[TranscriptSegment] = []
    for seg in segments_iter:
        txt = (seg.text or "").strip()
        if txt:
            raw.append(TranscriptSegment("Speaker 1", float(seg.start), float(seg.end), txt))

    # Lightweight heuristic speaker diarisation (gap-based)
    turns, spk, prev_end = [], 1, raw[0].start if raw else 0.0
    for i, seg in enumerate(raw):
        if i > 0 and seg.start - prev_end >= 1.2:
            spk = 2 if spk == 1 else 1
        turns.append(TranscriptSegment(f"Speaker {spk}", seg.start, seg.end, seg.text))
        prev_end = seg.end

    ts = get_audio_timestamps({"segments": [asdict(s) for s in turns]})

    return {
        "audio_file":             str(audio_path),
        "processed_at":           datetime.now(timezone.utc).isoformat(),
        "language":               getattr(info, "language", None),
        "language_probability":   getattr(info, "language_probability", None),
        # ── Timestamp block ────────────────────────────────────────────────────
        "timestamps": ts,
        # ── Raw segments ───────────────────────────────────────────────────────
        "segments":               [asdict(s) for s in turns],
        "text":                   "\n".join(
            f"{s.speaker} [{format_ts(s.start)}-{format_ts(s.end)}]: {s.text}"
            for s in turns
        ),
    }


# =========================
# STEP 1 — SUMMARISE
# =========================
_SUMMARISE_SYSTEM = (
    "You are a precise note-taker for a social services office. "
    "Extract every fact faithfully. Never add or invent information not in the transcript."
)
_SUMMARISE_USER = """Read the customer service transcript below.
Extract every factual detail into a concise bullet-point fact sheet.

Cover ALL of the following if present:
- Office/service location name
- Contact method (in-person / phone / email / remote)
- Date and time of visit
- How the customer heard about the service
- Number of customers
- Gender, age, or age group
- Country of origin / birth
- Native or mother tongue language
- Education level
- Employment or labor market status
- City/municipality of residence
- How long they have lived in Finland
- Reason for immigration
- Any special circumstances (illiterate, paperless, tourist, Ukraine crisis)
- Main reason(s) for coming / topics discussed
- What actions the advisor took
- What organisations or services were mentioned or referred to
- Any follow-up actions or appointments agreed

One fact per bullet. Plain English. No interpretation.

TRANSCRIPT:
{transcript}

FACT SHEET:"""


def summarise_transcript(transcript_text: str) -> str:
    import ollama
    print("\n[Step 1/2] Summarising transcript → fact sheet...")
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _SUMMARISE_SYSTEM},
            {"role": "user",   "content": _SUMMARISE_USER.format(transcript=transcript_text)},
        ],
        options={"temperature": 0.0, "num_predict": 1024},
    )
    fact_sheet = response["message"]["content"].strip()
    if DEBUG_LLM_RESPONSES:
        print(f"\n--- [FACT SHEET] ---\n{fact_sheet}\n---\n")
    return fact_sheet


# =========================
# STEP 2 — PER-QUESTION EXTRACTION
# Each question gets its own tailored system + user prompt.
# Input to LLM is the SHORT fact sheet, not the raw transcript.
# =========================
def _call_ollama_for_question(key: str, fact_sheet: str) -> str:
    import ollama

    prompts = QUESTION_PROMPTS.get(key)
    if not prompts or not prompts["user"]:
        return ""

    user_msg = prompts["user"].format(fact_sheet=fact_sheet)

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": prompts["system"]},
            {"role": "user",   "content": user_msg},
        ],
        options={"temperature": 0.0, "num_predict": 256},
    )
    raw = response["message"]["content"].strip()

    if DEBUG_LLM_RESPONSES:
        print(f"  [{key}] → {raw[:120]}")

    # Reject placeholder non-answers
    if raw.lower() in ("not mentioned", "not provided", "unknown", "n/a", "none", "null", "empty string", '""', "''"):
        return ""

    return normalize_answer(raw)


def extract_per_question(
    transcript_text: str,
    transcript_data: Dict[str, Any],
) -> Tuple[Dict[str, str], str]:
    """
    Two-step extraction:
      Step 1: Summarise full transcript → compact fact sheet (1 LLM call)
      Step 2: Ask each question against the fact sheet (1 LLM call per question)

    Using the fact sheet as input (not the raw transcript) keeps each question
    call short and focused — the key fix for small models like llama3.2.
    """
    # ── Step 1: summarise ─────────────────────────────────────────────────────
    fact_sheet = summarise_transcript(transcript_text)
    if not fact_sheet.strip():
        print("  ⚠ Summarisation empty — using raw transcript as fallback.")
        fact_sheet = transcript_text

    # ── Step 2: per-question extraction ───────────────────────────────────────
    ts_block = get_audio_timestamps(transcript_data)
    dur_sec  = ts_block.get("duration_seconds") or 0.0

    results: Dict[str, str] = {}
    total = len(FORM_QUESTIONS)

    print(f"\n[Step 2/2] Extracting {total} fields from fact sheet...\n")

    for idx, item in enumerate(FORM_QUESTIONS, 1):
        key = item["key"]

        # Deterministic fields — never sent to LLM
        if key == "visit_duration":
            results[key] = ts_block.get("duration_formatted", "")
            print(f"  [{idx:02d}/{total}] {key:30s} = {results[key]}  [computed]")
            continue

        print(f"  [{idx:02d}/{total}] {key:30s} ", end="", flush=True)
        try:
            answer = _call_ollama_for_question(key, fact_sheet)
        except Exception as e:
            print(f"FAILED ({e})")
            answer = ""

        results[key] = answer
        if not DEBUG_LLM_RESPONSES:
            # print inline only if not already printed by debug
            print(f"= {answer[:80] if answer else '(empty)'}")

    # ── Post-process enums ────────────────────────────────────────────────────
    results = postprocess(results)

    # Ensure all keys present
    for item in FORM_QUESTIONS:
        results.setdefault(item["key"], "")

    return results, fact_sheet


# =========================
# HEURISTIC FALLBACK  (no Ollama)
# =========================
def extract_heuristically(transcript_text: str, transcript_data: Dict[str, Any]) -> Dict[str, str]:
    text    = transcript_text.lower()
    ts      = get_audio_timestamps(transcript_data)
    result  = {item["key"]: "" for item in FORM_QUESTIONS}
    result["visit_duration"] = ts.get("duration_formatted", "")

    if any(k in text for k in ["guidance point", "advice point", "service market"]):
        result["control_location"] = "Service market Big Apple"
        result["contact_method"]   = "Visit to a guidance/advice point"

    for pat in [r"(\d+)\s*customer", r"number of customers[:\s]+(\d+)"]:
        m = re.search(pat, text)
        if m:
            result["number_of_customers"] = m.group(1)
            break

    topics = []
    for label, kws in {
        "Residence":                 ["residence", "permit", "registration"],
        "Benefits (e.g. Kela)":      ["kela", "benefit"],
        "Immigration process":       ["immigration", "citizenship"],
        "Legal matters":             ["lawyer", "legal", "court"],
        "Finance":                   ["tax", "debt", "bank", "finance"],
        "Health care":               ["health", "doctor", "hospital"],
        "Work":                      ["job", "work", "employment"],
        "Studying Finnish/Swedish":  ["finnish", "swedish", "language course"],
    }.items():
        if any(k in text for k in kws):
            topics.append(label)
    result["topics_of_discussion"] = "; ".join(topics)

    return {k: normalize_answer(v) for k, v in result.items()}


# =========================
# OUTPUT — JSON + CSV
# =========================
def build_output_json(
    transcript_data: Dict[str, Any],
    extracted: Dict[str, str],
    fact_sheet: str,
) -> Dict[str, Any]:
    """
    Build the final JSON payload.
    The 'timestamps' block is included at the top level so every
    conversation record carries its own precise timing data.
    """
    ts = transcript_data.get("timestamps", get_audio_timestamps(transcript_data))
    return {
        # ── Conversation-level metadata ─────────────────────────────────────
        "audio_file":   transcript_data.get("audio_file"),
        "processed_at": transcript_data.get("processed_at"),
        "language":     transcript_data.get("language"),
        # ── Timestamp block (prominently at top level) ──────────────────────
        "timestamps": {
            "conversation_start":    ts.get("conversation_start_ts"),
            "conversation_end":      ts.get("conversation_end_ts"),
            "duration_seconds":      ts.get("duration_seconds"),
            "duration_minutes":      ts.get("duration_minutes"),
            "duration_formatted":    ts.get("duration_formatted"),
            "start_raw_seconds":     ts.get("conversation_start_seconds"),
            "end_raw_seconds":       ts.get("conversation_end_seconds"),
        },
        # ── Intermediate fact sheet ──────────────────────────────────────────
        "fact_sheet": fact_sheet,
        # ── Extracted form answers ───────────────────────────────────────────
        "extracted_answers": extracted,
        # ── Full segment-level transcript ────────────────────────────────────
        "transcript": {
            "text":     transcript_data.get("text"),
            "segments": transcript_data.get("segments"),
        },
    }


def save_outputs(
    out_dir: Path,
    transcript_data: Dict[str, Any],
    extracted: Dict[str, str],
    fact_sheet: str,
) -> Tuple[Path, Path]:
    stem = Path(AUDIO_PATH).stem

    payload   = build_output_json(transcript_data, extracted, fact_sheet)
    json_path = out_dir / f"{stem}_transcript_and_answers.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    csv_path = out_dir / f"{stem}_answers.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Question", "Answer"])
        # Timestamp rows first so the CSV is self-documenting
        ts = payload["timestamps"]
        writer.writerow(["Conversation Start",    ts.get("conversation_start", "")])
        writer.writerow(["Conversation End",      ts.get("conversation_end", "")])
        writer.writerow(["Duration (formatted)",  ts.get("duration_formatted", "")])
        writer.writerow(["Duration (seconds)",    ts.get("duration_seconds", "")])
        writer.writerow(["---", "---"])
        for item in FORM_QUESTIONS:
            writer.writerow([item["question"], extracted.get(item["key"], "")])

    return json_path, csv_path


def ollama_available() -> bool:
    try:
        return subprocess.run(["ollama", "--version"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


# =========================
# MAIN
# =========================
def main() -> None:
    audio_path = Path(AUDIO_PATH).expanduser().resolve()
    out_dir    = ensure_output_dir()

    print(f"Transcribing: {audio_path}")
    transcript_data = transcribe_audio(audio_path)
    transcript_text = transcript_data["text"]

    ts = transcript_data["timestamps"]
    print(f"Language  : {transcript_data.get('language')} "
          f"(p={transcript_data.get('language_probability', 0):.2f})")
    print(f"Start     : {ts['conversation_start_ts']}  ({ts['conversation_start_seconds']}s)")
    print(f"End       : {ts['conversation_end_ts']}  ({ts['conversation_end_seconds']}s)")
    print(f"Duration  : {ts['duration_formatted']}  ({ts['duration_seconds']}s)")
    print(f"Segments  : {len(transcript_data['segments'])}")

    fact_sheet  = ""
    used_ollama = False

    if USE_OLLAMA_IF_AVAILABLE and ollama_available():
        try:
            extracted, fact_sheet = extract_per_question(transcript_text, transcript_data)
            used_ollama = True
        except Exception as e:
            print(f"\nOllama failed entirely ({e}), using heuristics.")
            extracted = extract_heuristically(transcript_text, transcript_data)
    else:
        print("Ollama not available — using heuristic extraction.")
        extracted = extract_heuristically(transcript_text, transcript_data)

    json_path, csv_path = save_outputs(out_dir, transcript_data, extracted, fact_sheet)

    print("\n=== EXTRACTED ANSWERS ===")
    for item in FORM_QUESTIONS:
        val    = extracted.get(item["key"], "")
        status = "✓" if val else "·"
        print(f"  {status} {item['question']:<40} {val}")

    filled = sum(1 for item in FORM_QUESTIONS if extracted.get(item["key"], ""))
    print(f"\n  {filled}/{len(FORM_QUESTIONS)} fields filled")
    print(f"\nUsed Ollama : {used_ollama}")
    print(f"JSON saved  : {json_path}")
    print(f"CSV saved   : {csv_path}")


if __name__ == "__main__":
    main()