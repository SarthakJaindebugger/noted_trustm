"""
admin_dashboard_stats.py

Placeholder data-access functions and variables for the Admin Dashboard fields.
Implementations should be replaced with real data queries (DB, analytics, or services).
Each function returns a JSON-serializable value suitable for returning from an API.
"""
import os
import json
import re
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USERS_ROOT = REPO_ROOT / "knowledgebase" / "users_admin_data" / "users"
DEFAULT_SUMMARY_OUTPUT = REPO_ROOT / "combined_admin_dashboard" / "combined_dashboard_summary.json"
CRM_JSON_NAMES = {"6_crm_form_parsed.json", "crm_form_parsed.json"}

FIELDS = [
    "Average Conversation time",
    "Contact Methods used",
    "Number of customers",
    "Gender Ratio",
    "Age groups",
    "Country of Origin",
    "Duration of residence in Finland",
    "Topics Discussed",
    "Purposes of visit",
    "Customer Feedbacks",
]


def _parse_duration(duration_str: Optional[str], fallback_seconds: Optional[float] = None) -> Optional[int]:
    if not duration_str:
        return int(fallback_seconds) if fallback_seconds is not None else None

    s = str(duration_str).strip().lower()
    if ":" in s:
        parts = [p for p in s.split(":") if p != ""]
        try:
            parts = [int(p) for p in parts]
        except Exception:
            parts = []
        if parts:
            parts = parts[::-1]
            secs = 0
            for i, v in enumerate(parts):
                secs += v * (60 ** i)
            return int(secs)

    hours = re.search(r"(\d+)\s*(?:h|hr|hour|hours)", s)
    minutes = re.search(r"(\d+)\s*(?:m|min|minute|minutes)", s)
    seconds = re.search(r"(\d+)\s*(?:s|sec|second|seconds)", s)

    total = 0
    found = False
    if hours:
        total += int(hours.group(1)) * 3600
        found = True
    if minutes:
        total += int(minutes.group(1)) * 60
        found = True
    if seconds:
        total += int(seconds.group(1))
        found = True

    if found:
        return int(total)

    simple_num = re.search(r"^(\d+)$", s)
    if simple_num:
        return int(simple_num.group(1))

    return int(fallback_seconds) if fallback_seconds is not None else None


def _format_duration(total_seconds: int) -> str:
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    parts.append(f"{seconds} sec")
    return " ".join(parts)


def _candidate_users_roots(source: Optional[Any] = None) -> List[Path]:
    roots: List[Path] = []
    if source is not None:
        if isinstance(source, (str, os.PathLike)):
            candidate = Path(source)
            if candidate.exists():
                roots.append(candidate)
        elif isinstance(source, Path):
            if source.exists():
                roots.append(source)

    env_root = os.environ.get("NOTED_USERS_ROOT")
    if env_root:
        env_path = Path(env_root)
        if env_path.exists():
            roots.append(env_path)

    if DEFAULT_USERS_ROOT.exists():
        roots.append(DEFAULT_USERS_ROOT)

    scratch_root = Path("/scratch/work/jains6/noted/noted-main/knowledgebase/users_admin_data/users")
    if scratch_root.exists():
        roots.append(scratch_root)

    unique_roots: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            unique_roots.append(root)
            seen.add(key)
    return unique_roots


def _find_final_crm_json_files(source: Optional[Any] = None) -> List[Path]:
    files: List[Path] = []
    seen = set()
    for root in _candidate_users_roots(source):
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            if path.name in CRM_JSON_NAMES:
                resolved = str(path.resolve())
                if resolved not in seen:
                    files.append(path)
                    seen.add(resolved)
    return sorted(files)


def build_combined_summary(source: Optional[Any] = None, output_path: Optional[Path] = None) -> Dict[str, Any]:
    json_files = _find_final_crm_json_files(source)
    records: List[Dict[str, Any]] = []
    for path in json_files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                records.append(data)
        except Exception:
            continue

    total_seconds = 0
    count = 0
    for record in records:
        metadata = record.get("metadata", {}) or {}
        visit_duration = metadata.get("visit_duration")
        audio_duration = metadata.get("audio_duration_sec")
        secs = _parse_duration(visit_duration, fallback_seconds=audio_duration)
        if secs is None:
            continue
        total_seconds += secs
        count += 1

    average_conversation_time = _format_duration(int(total_seconds / count)) if count else "—"

    contact_counter = Counter()
    for record in records:
        questionnaire = record.get("questionnaire", {}) or {}
        raw_answer = questionnaire.get("What is the contact method used by Advisee(s)?") or ""
        cleaned = str(raw_answer).strip()
        if not cleaned or cleaned.lower() in {"not mentioned in transcript.", "none", "n/a", "unknown"}:
            continue
        for item in [part.strip() for part in cleaned.split(",") if part.strip()]:
            contact_counter[item] += 1

    contact_methods = []
    if contact_counter:
        total = sum(contact_counter.values())
        for label, value in contact_counter.most_common():
            contact_methods.append({
                "label": label,
                "count": value,
                "pct": round(value / total * 100, 1),
            })

    summary = {
        "average_conversation_time": average_conversation_time,
        "contact_methods": contact_methods,
        "number_of_customers": len(records),
        "source_files": [str(path.relative_to(REPO_ROOT)).replace("\\", "/") for path in json_files],
    }

    target_path = output_path or DEFAULT_SUMMARY_OUTPUT
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return summary


def get_average_conversation_time(source: Optional[Any] = None, **kwargs) -> str:
    """Return average conversation time based on all discovered CRM JSON files."""
    return build_combined_summary(source=source)["average_conversation_time"]


def get_contact_methods(source: Optional[Any] = None, **kwargs) -> List[Dict[str, Any]]:
    """Return contact methods observed across all discovered CRM JSON files."""
    return build_combined_summary(source=source)["contact_methods"]


def get_number_of_customers(source: Optional[Any] = None, **kwargs) -> Union[int, str]:
    """Return the total number of analyzed audio files from all discovered CRM JSON files."""
    return build_combined_summary(source=source)["number_of_customers"]


def get_gender_ratio(source: Optional[Any] = None, **kwargs) -> str:
    """Return gender ratio as a string, e.g. '60% female / 40% male'."""
    data_dir = None
    if isinstance(source, str):
        data_dir = source
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    try:
        if not os.path.isdir(data_dir):
            return "—"

        counts = Counter()
        total_known = 0
        for fname in os.listdir(data_dir):
            if not fname.lower().endswith('.json'):
                continue
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
            except Exception:
                continue

            extraction = data.get('extraction', {}) if isinstance(data, dict) else {}
            gender_raw = extraction.get('Gender') or extraction.get('gender') or ''
            if not gender_raw:
                continue
            g = str(gender_raw).strip().lower()
            if not g or g in ('not specified', 'none', 'n/a', 'unknown', 'not available'):
                continue

            if g.startswith('f') or 'woman' in g or 'female' in g:
                counts['female'] += 1
                total_known += 1
            elif g.startswith('m') or 'man' in g or 'male' in g:
                counts['male'] += 1
                total_known += 1
            else:
                counts['other'] += 1
                total_known += 1

        if total_known == 0:
            return "—"

        def pct(n):
            return round((n / total_known) * 100, 1)

        parts = []
        if counts.get('female'):
            parts.append(f"{pct(counts['female']):.1f}% female")
        if counts.get('male'):
            parts.append(f"{pct(counts['male']):.1f}% male")
        if counts.get('other'):
            parts.append(f"{pct(counts['other']):.1f}% other")

        return ' / '.join(parts)
    except Exception:
        return "—"


def get_age_groups(source: Optional[Any] = None, **kwargs) -> List[Dict[str, Any]]:
    """Return age group distribution, e.g. [{'range':'18-25','pct':20}, ...]."""
    data_dir = None
    if isinstance(source, str):
        data_dir = source
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    # Predefined buckets
    buckets = [
        ("0-17", 0, 17),
        ("18-29", 18, 29),
        ("30-64", 30, 64),
        ("65+", 65, 200),
    ]

    def bucket_for_age_pair(a: int, b: int) -> str:
        avg = (a + b) / 2
        for name, lo, hi in buckets:
            if lo <= avg <= hi:
                return name
        return "Unknown"

    def bucket_for_single_age(a: int) -> str:
        for name, lo, hi in buckets:
            if lo <= a <= hi:
                return name
        return "Unknown"

    counts = Counter()
    total_known = 0

    try:
        if not os.path.isdir(data_dir):
            return []

        for fname in os.listdir(data_dir):
            if not fname.lower().endswith('.json'):
                continue
            fpath = os.path.join(data_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
            except Exception:
                continue

            extraction = data.get('extraction', {}) if isinstance(data, dict) else {}
            age_raw = extraction.get('Age_Group') or extraction.get('age_group') or ''
            if not age_raw:
                continue
            s = str(age_raw).strip()

            # Try to find numeric ranges like '18-29' or two numbers in text
            nums = re.findall(r"(\d{1,3})", s)
            if len(nums) >= 2:
                a = int(nums[0])
                b = int(nums[1])
                bucket = bucket_for_age_pair(a, b)
            elif len(nums) == 1:
                a = int(nums[0])
                bucket = bucket_for_single_age(a)
            else:
                low = s.lower()
                if 'young' in low:
                    bucket = '18-29'
                elif 'adult' in low:
                    bucket = '30-64'
                elif 'senior' in low or '65' in low or 'old' in low:
                    bucket = '65+'
                else:
                    bucket = 'Unknown'

            if bucket != 'Unknown':
                counts[bucket] += 1
                total_known += 1

    except Exception:
        return []

    if total_known == 0:
        return []

    # Build list of dicts sorted by bucket order
    results: List[Dict[str, Any]] = []
    for name, lo, hi in buckets:
        c = counts.get(name, 0)
        if c:
            pct = round((c / total_known) * 100, 1)
            results.append({"range": name, "count": c, "pct": pct})

    return results


def get_countries_of_origin(source: Optional[Any] = None, **kwargs) -> List[Dict[str, Any]]:
    """Return list of countries with percentages, e.g. [{'country':'Finland','pct':70}]."""
    # TODO: implement
    return []


def get_duration_of_residence(source: Optional[Any] = None, **kwargs) -> List[Dict[str, Any]]:
    """Return distribution of residence durations, e.g. [{'range':'<1yr','pct':10}]."""
    # TODO: implement
    return []








def get_topics_discussed(
    source: Optional[Any] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Extract and categorize topics from CSV files into 15 predefined categories.
    Returns list of dicts with category name, count, and percentage.
    """
    
    # Define the 15 topic categories
    PREDEFINED_TOPICS = [
        "Residence Benefits (e.g. Kela)",
        "Hobbies and Leisure",
        "Education",
        "Crisis Situations",
        "Immigration Process",
        "Legal Matters",
        "Family Life",
        "Police Matters",
        "Social Affairs",
        "Studying Finnish/Swedish",
        "Finance",
        "Health Care",
        "Working Conditions",
        "Career Guidance",
        "Other"
    ]

    # Mapping rules: keywords to category index
    CATEGORY_KEYWORDS = {
        0: ["kela", "residence benefit", "allowance", "unemployment", "disability", "pension"],
        1: ["hobby", "leisure", "hobby", "sport", "game", "recreation", "entertainment"],
        2: ["education", "school", "university", "study", "course", "training", "degree"],
        3: ["crisis", "emergency", "violence", "domestic", "abuse", "conflict", "danger"],
        4: ["residence", "permit", "visa", "citizenship", "registration", "immigration", "foreigner"],
        5: ["legal", "law", "rights", "contract", "agreement", "lawyer", "court"],
        6: ["family", "child", "children", "daycare", "kindergarten", "school", "parent", "relationship", "marriage"],
        7: ["police", "crime", "offense", "criminal", "arrest", "security"],
        8: ["social", "social work", "guidance", "counseling", "help", "support", "welfare"],
        9: ["finnish", "swedish", "language", "course", "learn"],
        10: ["finance", "tax", "taxation", "debt", "bill", "banking", "consumer", "money", "payment"],
        11: ["health", "doctor", "hospital", "medical", "care", "medicine"],
        12: ["working condition", "occupational", "health safety", "work environment", "workplace", "employment"],
        13: ["career", "job", "work", "employment", "freelance", "entrepreneurship"],
        14: []  # Other - default category
    }

    if isinstance(source, str):
        data_dir = source
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    INVALID_VALUES = {
        "", "none", "not specified", "n/a", "na", "unknown", "-", "--",
    }

    category_counts = Counter()

    def map_topic_to_category(topic_text: str) -> int:
        """Map a topic string to one of the 15 categories."""
        topic_lower = topic_text.lower().strip()
        
        # Check each category's keywords
        for category_idx, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in topic_lower:
                    return category_idx
        
        # Default to "Other"
        return 14

    try:
        if not os.path.isdir(data_dir):
            return []

        for fname in os.listdir(data_dir):
            if not fname.lower().endswith(".csv"):
                continue

            fpath = os.path.join(data_dir, fname)

            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)

                    if (
                        reader.fieldnames is None
                        or "Question" not in reader.fieldnames
                        or "Answer" not in reader.fieldnames
                    ):
                        continue

                    for row in reader:
                        if row.get("Question", "").strip().lower() != "topics":
                            continue

                        answer = (row.get("Answer", "") or "").strip()

                        if not answer or answer.lower() in INVALID_VALUES:
                            continue

                        # Remove common LLM boilerplate
                        answer = re.sub(
                            r"the topics discussed in this visit are\s*:?",
                            "", answer, flags=re.IGNORECASE
                        )
                        answer = re.sub(
                            r"the topic discussed in this visit is\s*:?",
                            "", answer, flags=re.IGNORECASE
                        )

                        # Extract numbered items or split by delimiters
                        extracted_topics = re.findall(
                            r"\d+\.\s*(.*?)(?=\d+\.|$)",
                            answer, flags=re.DOTALL
                        )

                        if not extracted_topics:
                            extracted_topics = re.split(r",|;|\n", answer)

                        for topic in extracted_topics:
                            # Clean up topic
                            topic = re.sub(r"\([^)]*\)", "", topic)
                            topic = re.sub(r"\s+", " ", topic).strip()
                            topic = topic.strip(" .:-")

                            if not topic or len(topic) < 2 or topic.lower() in INVALID_VALUES:
                                continue

                            # Map to category and increment counter
                            category_idx = map_topic_to_category(topic)
                            category_counts[category_idx] += 1

            except Exception:
                continue

    except Exception:
        return []

    # Build result list with all 15 categories (including those with 0 count)
    total_count = sum(category_counts.values())

    result = []
    for idx, category_name in enumerate(PREDEFINED_TOPICS):
        count = category_counts.get(idx, 0)
        pct = round((count / total_count) * 100, 1) if total_count > 0 else 0.0
        result.append({
            "topic": category_name,
            "count": count,
            "pct": pct
        })

    return result






def get_purposes_of_visit(source: Optional[Any] = None, top_k: int = 10, **kwargs) -> List[str]:
    """Return most common purposes of visit (strings)."""
    # TODO: implement
    return []


def get_customer_feedbacks(source: Optional[Any] = None, limit: int = 20, **kwargs) -> List[Dict[str, Any]]:
    """Return recent customer feedback entries as list of dicts with `text` and optional `rating`."""
    # TODO: implement
    return []


def fetch_all_stats(source: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
    """Return a dictionary containing the aggregated dashboard fields for all CRM JSON files."""
    summary = build_combined_summary(source=source)
    return {
        "average_conversation_time": summary["average_conversation_time"],
        "contact_methods": summary["contact_methods"],
        "number_of_customers": summary["number_of_customers"],
        "gender_ratio": get_gender_ratio(source, **kwargs),
        "age_groups": get_age_groups(source, **kwargs),
        "country_of_origin": get_countries_of_origin(source, **kwargs),
        "duration_of_residence": get_duration_of_residence(source, **kwargs),
        "topics_discussed": get_topics_discussed(source, **kwargs),
        "purposes_of_visit": get_purposes_of_visit(source, **kwargs),
        "customer_feedbacks": get_customer_feedbacks(source, **kwargs),
        "source_files": summary["source_files"],
    }


__all__ = [
    "FIELDS",
    "get_average_conversation_time",
    "get_contact_methods",
    "get_number_of_customers",
    "get_gender_ratio",
    "get_age_groups",
    "get_countries_of_origin",
    "get_duration_of_residence",
    "get_topics_discussed",
    "get_purposes_of_visit",
    "get_customer_feedbacks",
    "fetch_all_stats",
]
