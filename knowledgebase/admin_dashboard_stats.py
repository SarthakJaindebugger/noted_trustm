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
from typing import Any, Dict, List, Optional, Union
from collections import Counter

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


def get_average_conversation_time(source: Optional[Any] = None, **kwargs) -> str:
    """Return average conversation time (human readable or seconds)."""
    # If a source directory is provided use it, otherwise read from default data folder
    output_dir = None
    if isinstance(source, str):
        output_dir = source
    else:
        # default to the sibling data directory
        output_dir = os.path.join(os.path.dirname(__file__), "data")

    def parse_duration(duration_str: Optional[str], fallback_seconds: Optional[float] = None) -> Optional[int]:
        if not duration_str:
            return int(fallback_seconds) if fallback_seconds is not None else None
        s = str(duration_str).strip().lower()
        # format mm:ss or hh:mm:ss
        if ":" in s:
            parts = [p for p in s.split(":") if p != ""]
            try:
                parts = [int(p) for p in parts]
            except Exception:
                # fall back to regex parsing
                parts = []
            if parts:
                # right-most is seconds
                parts = parts[::-1]
                secs = 0
                for i, v in enumerate(parts):
                    secs += v * (60 ** i)
                return int(secs)

        # regex for hours, minutes, seconds
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

        # try to extract any number as seconds
        simple_num = re.search(r"^(\d+)$", s)
        if simple_num:
            return int(simple_num.group(1))

        # fallback to provided seconds value
        return int(fallback_seconds) if fallback_seconds is not None else None

    total_secs = 0
    count = 0

    try:
        if os.path.isdir(output_dir):
            for fname in os.listdir(output_dir):
                if not fname.lower().endswith('.json'):
                    continue
                fpath = os.path.join(output_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as fh:
                        data = json.load(fh)
                except Exception:
                    continue

                metadata = data.get('metadata', {}) if isinstance(data, dict) else {}
                visit_duration = metadata.get('visit_duration')
                audio_secs = metadata.get('audio_duration_sec')
                secs = parse_duration(visit_duration, fallback_seconds=audio_secs)
                if secs is None:
                    continue
                total_secs += secs
                count += 1
    except Exception:
        return "—"

    if count == 0:
        return "—"

    avg = int(total_secs / count)

    # format human readable
    hours, rem = divmod(avg, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    parts.append(f"{seconds} sec")
    return " ".join(parts)


def get_contact_methods(source: Optional[Any] = None, **kwargs) -> List[str]:
    """Return list of contact methods observed (e.g. ['phone', 'email'])."""
    # TODO: implement
    return []


def get_number_of_customers(source: Optional[Any] = None, **kwargs) -> Union[int, str]:
    """Return total number of customers based on unique JSON files in the data folder.

    Counts files ending with `.json` in the `data` directory (or in `source` if
    a directory path is provided). Returns integer count or placeholder "—"
    on error or when directory is missing.
    """
    data_dir = None
    if isinstance(source, str):
        data_dir = source
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    try:
        if not os.path.isdir(data_dir):
            return "—"

        files = os.listdir(data_dir)
        # Count unique JSON files (by filename)
        json_files = [f for f in files if f.lower().endswith('.json')]
        return len(json_files)
    except Exception:
        return "—"


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
    top_k: int = 15,
    **kwargs
) -> List[str]:
    """
    Extract human-readable topic phrases from Topic answers.
    Returns phrases instead of individual keywords.
    """

    import os
    import csv
    import re
    from collections import Counter

    if isinstance(source, str):
        data_dir = source
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "data")

    INVALID_VALUES = {
        "",
        "none",
        "not specified",
        "n/a",
        "na",
        "unknown",
        "-",
        "--",
    }

    topic_counter = Counter()

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

                        if (
                            row.get("Question", "")
                            .strip()
                            .lower()
                            != "topics"
                        ):
                            continue

                        answer = (
                            row.get("Answer", "") or ""
                        ).strip()

                        if not answer:
                            continue

                        if answer.lower() in INVALID_VALUES:
                            continue

                        # Remove common LLM boilerplate
                        answer = re.sub(
                            r"the topics discussed in this visit are\s*:?",
                            "",
                            answer,
                            flags=re.IGNORECASE,
                        )

                        answer = re.sub(
                            r"the topic discussed in this visit is\s*:?",
                            "",
                            answer,
                            flags=re.IGNORECASE,
                        )

                        extracted_topics = re.findall(
                            r"\d+\.\s*(.*?)(?=\d+\.|$)",
                            answer,
                            flags=re.DOTALL,
                        )

                        if not extracted_topics:
                            extracted_topics = re.split(
                                r",|;|\n",
                                answer
                            )

                        for topic in extracted_topics:

                            topic = re.sub(
                                r"\([^)]*\)",
                                "",
                                topic
                            )

                            topic = re.sub(
                                r"\s+",
                                " ",
                                topic
                            ).strip()

                            topic = topic.strip(" .:-")

                            if not topic:
                                continue

                            if topic.lower() in INVALID_VALUES:
                                continue

                            # Remove leading numbering again if present
                            topic = re.sub(
                                r"^\d+\.\s*",
                                "",
                                topic
                            )

                            # Ignore tiny fragments
                            if len(topic) < 4:
                                continue

                            topic_counter[topic.title()] += 1

            except Exception:
                continue

    except Exception:
        return []

    if not topic_counter:
        return []

    total_topics = sum(topic_counter.values())

    return [
        {
            "topic": topic,
            "count": count,
            "pct": round((count / total_topics) * 100, 1)
        }
        for topic, count in topic_counter.most_common(top_k)
    ]






def get_purposes_of_visit(source: Optional[Any] = None, top_k: int = 10, **kwargs) -> List[str]:
    """Return most common purposes of visit (strings)."""
    # TODO: implement
    return []


def get_customer_feedbacks(source: Optional[Any] = None, limit: int = 20, **kwargs) -> List[Dict[str, Any]]:
    """Return recent customer feedback entries as list of dicts with `text` and optional `rating`."""
    # TODO: implement
    return []


def fetch_all_stats(source: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
    """Return a dictionary containing all dashboard fields using the helper functions above.

    Keep this function as a single place the API can call to retrieve dashboard data.
    """
    return {
        "average_conversation_time": get_average_conversation_time(source, **kwargs),
        "contact_methods": get_contact_methods(source, **kwargs),
        "number_of_customers": get_number_of_customers(source, **kwargs),
        "gender_ratio": get_gender_ratio(source, **kwargs),
        "age_groups": get_age_groups(source, **kwargs),
        "country_of_origin": get_countries_of_origin(source, **kwargs),
        "duration_of_residence": get_duration_of_residence(source, **kwargs),
        "topics_discussed": get_topics_discussed(source, **kwargs),
        "purposes_of_visit": get_purposes_of_visit(source, **kwargs),
        "customer_feedbacks": get_customer_feedbacks(source, **kwargs),
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
