from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from speech_analysis_qa.utils import sanitize_username

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USERS_ROOT = REPO_ROOT / "knowledgebase" / "users_admin_data" / "users"
SUBMITTED_CRM_ROOT = REPO_ROOT / "knowledgebase" / "submitted_crm_forms"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


def get_submitted_crm_root() -> Path:
    """Resolve the submitted CRM forms directory with fallback support for HPC cluster.
    
    Priority:
    1. SUBMITTED_CRM_FORMS_DIR environment variable
    2. Config settings storage.crm_dir
    3. REPO_ROOT / "knowledgebase" / "submitted_crm_forms"
    """
    import logging
    logger = logging.getLogger(__name__)
    
    candidates: list[Path] = []
    
    env_crm_dir = os.getenv("SUBMITTED_CRM_FORMS_DIR")
    if env_crm_dir:
        logger.info(f"[CRM_PATH] Using SUBMITTED_CRM_FORMS_DIR from environment: {env_crm_dir}")
        candidates.append(Path(env_crm_dir))
    
    try:
        from config import settings
        configured_crm_dir = getattr(getattr(settings, "storage", None), "crm_dir", None)
        if configured_crm_dir:
            logger.info(f"[CRM_PATH] Using crm_dir from config: {configured_crm_dir}")
            candidates.append(Path(configured_crm_dir))
    except Exception as exc:
        logger.debug(f"[CRM_PATH] Could not load config: {exc}")
        settings = None
    
    candidates.append(REPO_ROOT / "knowledgebase" / "submitted_crm_forms")
    
    for candidate in candidates:
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        candidate = candidate.resolve()
        logger.info(f"[CRM_PATH] Checking candidate: {candidate}")
        
        # Test write permission
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.touch()
            test_file.unlink()
            logger.info(f"[CRM_PATH] Selected CRM directory: {candidate}")
            return candidate
        except Exception as exc:
            logger.debug(f"[CRM_PATH] Candidate {candidate} not writable: {exc}")
            continue
    
    # Fallback: return the last candidate and let mkdir handle it
    final = (REPO_ROOT / "knowledgebase" / "submitted_crm_forms").resolve()
    logger.info(f"[CRM_PATH] Using fallback CRM directory: {final}")
    return final


def get_default_users_root() -> Path:
    candidates: list[Path] = []

    env_data_dir = os.getenv("NOTED_DATA_DIR")
    if env_data_dir:
        candidates.append(Path(env_data_dir))

    try:
        from config import settings
    except Exception:
        settings = None

    if settings is not None:
        configured_data_dir = getattr(getattr(settings, "storage", None), "data_dir", None)
        if configured_data_dir:
            candidates.append(Path(configured_data_dir))

    candidates.append(REPO_ROOT / "knowledgebase" / "users_admin_data")
    candidates.append(DEFAULT_USERS_ROOT)

    for candidate in candidates:
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        candidate = candidate.resolve()
        if candidate.name == "users":
            return candidate
        if candidate.exists() and (candidate / "users").exists():
            return (candidate / "users").resolve()
        if candidate.exists() and candidate.is_dir():
            return (candidate / "users").resolve()

    return (REPO_ROOT / "knowledgebase" / "users_admin_data" / "users").resolve()


def resolve_audio_path(audio_path: str | Path, repo_root: Optional[Path] = None) -> Path:
    repo_root = repo_root or REPO_ROOT
    candidate = Path(audio_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def infer_username(audio_path: str | Path, users_root: Optional[Path] = None) -> Optional[str]:
    users_root = (users_root or get_default_users_root()).resolve()
    resolved = resolve_audio_path(audio_path)
    try:
        relative = resolved.relative_to(users_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return relative.parts[0]


def list_user_audio_files(users_root: Optional[Path] = None) -> list[dict]:
    users_root = (users_root or get_default_users_root()).resolve()
    if not users_root.exists():
        return []

    audio_files: list[dict] = []
    for path in sorted(users_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            relative_path = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        username = infer_username(path, users_root)
        audio_files.append({
            "path": str(relative_path).replace("\\", "/"),
            "display_name": f"{username or 'unknown'} / {path.name}",
            "name": path.name,
            "username": username,
        })

    return audio_files


def list_audio_files_for_username(username: str, users_root: Optional[Path] = None) -> list[dict]:
    """Return only the audio files that belong to the given username.

    This is used by the user dashboard so a logged-in user can see and analyze
    only their own recordings (saved under users/<username>/recordings or
    users/<username>/uploads).
    """
    users_root = (users_root or get_default_users_root()).resolve()
    if not users_root.exists():
        return []

    safe_username = sanitize_username(username)
    user_root = users_root / safe_username
    if not user_root.exists():
        return []

    audio_files: list[dict] = []
    for path in sorted(user_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            relative_path = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        audio_files.append({
            "path": str(relative_path).replace("\\", "/"),
            "display_name": path.name,
            "name": path.name,
            "username": safe_username,
        })

    return audio_files


def list_audio_files_categorized_for_username(username: str, users_root: Optional[Path] = None) -> dict:
    """Return audio files split into 'completed' (CRM form exists in uploads) and 'new'.

    An audio file is considered completed if any directory in the user's uploads/
    folder whose name starts with the audio's base stem (text before the first '_')
    contains a CRM form file (6_crm_form.html or 6_crm_form_parsed.json).
    """
    users_root = (users_root or get_default_users_root()).resolve()
    if not users_root.exists():
        return {"completed": [], "new": []}

    safe_username = sanitize_username(username)
    user_root = users_root / safe_username
    if not user_root.exists():
        return {"completed": [], "new": []}

    uploads_dir = user_root / "uploads"

    # Build set of base stems that have a CRM form in uploads
    completed_stems: set[str] = set()
    if uploads_dir.exists():
        for d in uploads_dir.iterdir():
            if not d.is_dir():
                continue
            has_crm = any(
                (d / name).exists()
                for name in ("6_crm_form.html", "6_crm_form_parsed.json", "crm_form_parsed.html", "crm_form_parsed.json")
            )
            if has_crm:
                # The base stem is the part before the first '_' in the directory name
                base_stem = d.name.split("_")[0] if "_" in d.name else d.name
                completed_stems.add(base_stem)

    completed: list[dict] = []
    new: list[dict] = []

    for path in sorted(user_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            relative_path = path.relative_to(REPO_ROOT)
        except ValueError:
            continue

        audio_stem = path.stem.split("_")[0] if "_" in path.stem else path.stem
        entry = {
            "path": str(relative_path).replace("\\", "/"),
            "display_name": path.name,
            "name": path.name,
            "username": safe_username,
        }

        if audio_stem in completed_stems:
            completed.append(entry)
        else:
            new.append(entry)

    return {"completed": completed, "new": new}


def ensure_audio_belongs_to_user(audio_path: str | Path, username: str, users_root: Optional[Path] = None) -> Path:
    """Validate that the audio file belongs to the given username.

    Raises ValueError if the file is not under the user's own directory tree.
    Returns the resolved audio path.
    """
    users_root = (users_root or get_default_users_root()).resolve()
    resolved = resolve_audio_path(audio_path)
    inferred = infer_username(resolved, users_root)
    if inferred != sanitize_username(username):
        raise ValueError("Selected audio file does not belong to this user")
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Audio file not found: {resolved}")
    return resolved


def build_analysis_output_paths(audio_path: str | Path, users_root: Optional[Path] = None, now: Optional[datetime] = None) -> tuple[Path, Path, Path, str]:
    users_root = (users_root or get_default_users_root()).resolve()
    resolved_audio = resolve_audio_path(audio_path)
    username = infer_username(resolved_audio, users_root)
    if not username:
        raise ValueError("Selected audio file is not under the configured users directory")

    user_root = users_root / sanitize_username(username)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_audio.stem).strip("._-") or "audio"
    stamp_dt = now or datetime.now()
    stamp = stamp_dt.strftime("%d-%m-%Y_%H%M")

    target_dir = user_root / "uploads" / f"{safe_stem}_{stamp}"
    embedding_dir = user_root / "embedding" / f"{safe_stem}_{stamp}"
    pipeline_parent_dir = target_dir.parent
    return target_dir, embedding_dir, pipeline_parent_dir, username


def analyze_audio_file(audio_path: str | Path, users_root: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    target_dir, embedding_dir, pipeline_parent_dir, username = build_analysis_output_paths(audio_path, users_root, now)

    # ── Skip logic: if this audio was already analyzed, return the existing result ──
    # Look for the most recently completed output dir for this audio stem
    resolved_audio = resolve_audio_path(audio_path)
    import re as _re
    audio_stem = _re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_audio.stem).strip("._-")
    uploads_dir = target_dir.parent  # .../users/<username>/uploads/

    if uploads_dir.exists():
        # Find all dirs for this stem, pick most recent
        existing_dirs = sorted(
            [d for d in uploads_dir.iterdir() if d.is_dir() and d.name.startswith(audio_stem)],
            reverse=True,
        )
        for existing_dir in existing_dirs:
            # Consider "complete" if the CRM HTML exists (last pipeline stage)
            crm_html_candidates = [existing_dir / "crm_form_parsed.html", existing_dir / "6_crm_form.html"]
            crm_json_candidates = [existing_dir / "crm_form_parsed.json", existing_dir / "6_crm_form_parsed.json"]
            crm_html = next((c for c in crm_html_candidates if c.exists()), None)
            crm_json = next((c for c in crm_json_candidates if c.exists()), None)
            if crm_html and crm_json:
                print(f"[SKIP] Analysis already exists for {resolved_audio.name} → {existing_dir.name}")
                return {
                    "output_dir": str(existing_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "crm_form_json_path": str(crm_json.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "crm_form_html_path": str(crm_html.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "result": None,
                    "skipped": True,
                }

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    embedding_dir.mkdir(parents=True, exist_ok=True)

    if not resolved_audio.exists() or not resolved_audio.is_file():
        raise FileNotFoundError(f"Audio file not found: {resolved_audio}")

    from speech_analysis_qa.speech_pipeline.run_pipeline import run_pipeline

    pipeline_output_dir = target_dir.parent
    try:
        result = run_pipeline(
            str(resolved_audio),
            str(pipeline_output_dir),
            embedding_dir=str(embedding_dir),
            username=username,
            cleanup_stage1=True,
            cleanup_llm=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Speech pipeline failed for {resolved_audio}: {exc}") from exc

    nested_output_dir = pipeline_output_dir / resolved_audio.stem
    if nested_output_dir.exists() and nested_output_dir != target_dir:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in nested_output_dir.iterdir():
            shutil.move(str(child), str(target_dir / child.name))
        nested_output_dir.rmdir()

    crm_form_json_path = None
    crm_form_html_path = None
    for candidate in (target_dir / "crm_form_parsed.json", target_dir / "6_crm_form_parsed.json"):
        if candidate.exists():
            crm_form_json_path = str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            break

    for candidate in (target_dir / "crm_form_parsed.html", target_dir / "6_crm_form.html"):
        if candidate.exists():
            crm_form_html_path = str(candidate.relative_to(REPO_ROOT)).replace("\\", "/")
            break

    return {
        "output_dir": str(target_dir.relative_to(REPO_ROOT)).replace("\\", "/"),
        "crm_form_json_path": crm_form_json_path,
        "crm_form_html_path": crm_form_html_path,
        "result": result,
    }


def check_crm_form_exists(
    username: str,
    audio_filename: str,
    submitted_crm_root: Optional[Path] = None,
) -> bool:
    """Check if a submitted CRM form exists for this audio file.
    
    Returns True if any CRM form file starting with username_ exists in the folder.
    In the current implementation, we track CRM forms by username + timestamp, not by audio filename.
    So this checks if ANY submitted form exists for this user (indicating they've run analysis).
    
    For a more precise check, you could parse the timestamps and match against analysis timestamps,
    but for MVP, we assume: if a submitted form exists, analysis was done.
    """
    if submitted_crm_root is None:
        root = get_submitted_crm_root()
    else:
        root = submitted_crm_root.resolve()
    
    if not root.exists():
        return False
    
    safe_username = sanitize_username(username)
    for file_path in root.glob(f"{safe_username}_*.json"):
        if file_path.is_file():
            return True
    return False


def aggregate_all_crm_forms(submitted_crm_root: Optional[Path] = None) -> dict:
    """Aggregate data from ALL submitted CRM forms for dashboard initialization.

    Reads from the actual 6_crm_form_parsed.json structure:
      - record["questionnaire"]  — AI-extracted string answers
      - record["form"]           — parsed array/scalar form fields
      - record["metadata"]       — timing and speaker data
    """
    SKIP = {"Not mentioned in transcript.", "", None}

    def _add(collection: set, value):
        """Add value (string or list) to set, skipping empties."""
        if isinstance(value, list):
            for v in value:
                v = str(v).strip() if v else ""
                if v and v not in SKIP:
                    collection.add(v)
        elif value and str(value).strip() not in SKIP:
            collection.add(str(value).strip())

    if submitted_crm_root is None:
        root = get_submitted_crm_root()
    else:
        root = submitted_crm_root.resolve()

    empty = {
        "contact_methods": [], "topics_discussed": [], "labour_positions": [],
        "birth_countries": [], "languages": [], "residences": [],
        "purposes_of_visit": [], "duration_of_residence": [], "directed_to": [],
        "heard_from": [], "immigration_reasons": [], "education_levels": [],
        "additional_info_tags": [], "other_feedback": [],
        "visit_durations": [], "customer_counts": [],
        "total_forms": 0, "number_of_customers": 0,
        "average_conversation_time": "—", "gender_ratio": "—",
        "age_groups": {"0-10": 0, "10-20": 0, "20-30": 0, "30-50": 0, "50+": 0},
        "gender_counts": {"Male": 0, "Female": 0},
    }
    if not root.exists():
        return empty

    agg = {k: set() for k in [
        "contact_methods", "topics_discussed", "labour_positions",
        "birth_countries", "languages", "residences",
        "purposes_of_visit", "duration_of_residence", "directed_to",
        "heard_from", "immigration_reasons", "education_levels",
        "additional_info_tags", "other_feedback",
    ]}
    agg["total_forms"] = 0
    agg["customer_counts"] = []
    agg["visit_durations"] = []
    unique_usernames = set()
    age_groups = {"0-10": 0, "10-20": 0, "20-30": 0, "30-50": 0, "50+": 0}
    gender_counts = {"Male": 0, "Female": 0}
    total_duration_sec = 0.0
    duration_count = 0

    for file_path in root.glob("*.json"):
        if not file_path.is_file():
            continue
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                record = json.load(fh)
        except Exception:
            continue

        agg["total_forms"] += 1

        # Extract username from filename: <username>_<DD.MM.YYYY>_<HH>_<MM>_<SS>.json
        fname = file_path.stem
        date_match = re.search(r"_\d{2}\.\d{2}\.\d{4}_", fname)
        if date_match:
            unique_usernames.add(fname[:date_match.start()])

        q = record.get("questionnaire", {})
        f = record.get("form", {})
        m = record.get("metadata", {})

        # ── Contact method ──
        # Prefer form.contactMethod (array), fall back to questionnaire string
        cm = f.get("contactMethod")
        if cm:
            _add(agg["contact_methods"], cm)
        else:
            _add(agg["contact_methods"], q.get("What is the contact method used by Advisee(s)?"))

        # ── Topics (Contents of the customer visit) ──
        contents = f.get("contents")
        if contents:
            _add(agg["topics_discussed"], contents)
            if f.get("contentsOther"):
                _add(agg["topics_discussed"], f["contentsOther"])
        else:
            raw = q.get("Contents of the customer visit", "")
            if raw and raw not in SKIP:
                for part in raw.split(","):
                    _add(agg["topics_discussed"], part.strip().rstrip(")"))

        # ── Purpose of visit ──
        purpose = f.get("purpose")
        if purpose:
            _add(agg["purposes_of_visit"], purpose)
        else:
            raw = q.get("Purpose of visit", "")
            if raw and raw not in SKIP:
                for part in raw.split(","):
                    _add(agg["purposes_of_visit"], part.strip())

        # ── Labour position ──
        labour = f.get("labourPosition")
        if labour:
            _add(agg["labour_positions"], labour)
        else:
            raw = q.get("Position in labour market", "")
            if raw and raw not in SKIP:
                for part in raw.split(","):
                    _add(agg["labour_positions"], part.strip())

        # ── Birth country ──
        _add(agg["birth_countries"], f.get("birthCountry") or q.get("Customer birth country"))

        # ── Mother tongue / language ──
        _add(agg["languages"], f.get("motherTongue") or q.get("Mother Tongue/Language"))

        # ── Domicile / residence ──
        _add(agg["residences"], f.get("domicile") or q.get("Customer Domicile"))

        # ── Duration of residence ──
        dur = f.get("residenceDuration")
        if dur:
            _add(agg["duration_of_residence"], dur)
        else:
            raw = q.get("Duration of residence in Finland", "")
            if raw and raw not in SKIP:
                for part in raw.split(","):
                    _add(agg["duration_of_residence"], part.strip())

        # ── Where directed ──
        _add(agg["directed_to"], f.get("directedTo") or q.get("Where the customer is directed"))

        # ── Heard from ──
        _add(agg["heard_from"], f.get("heardFrom") or q.get("Heard from the guidance/advice position (if other where?)"))

        # ── Immigration reason ──
        _add(agg["immigration_reasons"], f.get("immigrationReason") or q.get("Reason for Immigration"))

        # ── Education level ──
        _add(agg["education_levels"], f.get("educationLevel") or q.get("Education Level"))

        # ── Additional info tags ──
        ai = f.get("additionalInfo")
        if ai:
            _add(agg["additional_info_tags"], [x for x in ai if x != "__other__"])
            if f.get("additionalInfoOther"):
                _add(agg["additional_info_tags"], f["additionalInfoOther"])
        else:
            _add(agg["additional_info_tags"], q.get("Additional Information about the customers"))

        # ── Other feedback ──
        _add(agg["other_feedback"], f.get("otherFeedback") or q.get("Any other Feedback"))

        # ── Visit duration ──
        vd = f.get("visitDuration") or m.get("visit_duration")
        if vd and vd not in SKIP:
            agg["visit_durations"].append(vd)

        # ── Customer count ──
        cc = f.get("customerCount")
        if cc and isinstance(cc, (int, float)) and cc > 0:
            agg["customer_counts"].append(int(cc))

        # ── Customer age ──
        age_val = f.get("age") or q.get("Customer Age")
        if age_val and age_val != "Not mentioned in transcript.":
            try:
                age = int(age_val) if isinstance(age_val, (int, float)) else int(re.search(r"\d+", str(age_val)).group())
                if age <= 10:
                    age_groups["0-10"] += 1
                elif age <= 20:
                    age_groups["10-20"] += 1
                elif age <= 30:
                    age_groups["20-30"] += 1
                elif age <= 50:
                    age_groups["30-50"] += 1
                else:
                    age_groups["50+"] += 1
            except (ValueError, TypeError, AttributeError):
                pass

        # ── Customer gender ──
        gender_val = f.get("gender") or q.get("Customer Gender")
        if gender_val and gender_val != "Not mentioned in transcript.":
            g = str(gender_val).strip().capitalize()
            if g in ("Male", "Female"):
                gender_counts[g] += 1

        # ── Average conversation time ──
        dur_sec = m.get("audio_duration_sec", 0) or 0
        if dur_sec > 0:
            total_duration_sec += dur_sec
            duration_count += 1

    # Build average conversation time string
    avg_time = "—"
    if duration_count > 0:
        avg_sec = total_duration_sec / duration_count
        mins = int(avg_sec // 60)
        secs = int(avg_sec % 60)
        avg_time = f"{mins} min {secs} sec"

    total_customers = len(unique_usernames) if unique_usernames else agg["total_forms"]

    return {
        "contact_methods":       sorted(agg["contact_methods"]),
        "topics_discussed":      sorted(agg["topics_discussed"]),
        "labour_positions":      sorted(agg["labour_positions"]),
        "birth_countries":       sorted(agg["birth_countries"]),
        "languages":             sorted(agg["languages"]),
        "residences":            sorted(agg["residences"]),
        "purposes_of_visit":     sorted(agg["purposes_of_visit"]),
        "duration_of_residence": sorted(agg["duration_of_residence"]),
        "directed_to":           sorted(agg["directed_to"]),
        "heard_from":            sorted(agg["heard_from"]),
        "immigration_reasons":   sorted(agg["immigration_reasons"]),
        "education_levels":      sorted(agg["education_levels"]),
        "additional_info_tags":  sorted(agg["additional_info_tags"]),
        "other_feedback":        sorted(agg["other_feedback"]),
        "total_forms":           agg["total_forms"],
        "number_of_customers":   total_customers,
        "average_conversation_time": avg_time,
        "gender_ratio": "—",
        "age_groups":            age_groups,
        "gender_counts":         gender_counts,
    }


def list_submitted_crm_forms(submitted_crm_root: Optional[Path] = None) -> list[dict]:
    """List all submitted CRM forms with metadata.
    
    Returns a list of dicts with: username, audio_filename, date, time, file_path, form_data
    Filename format: <username>_<DD.MM.YYYY>_<HH>_<MM>_<SS>.json
    e.g. demo_04.08.2026_12_30_45.json
    """
    if submitted_crm_root is None:
        root = get_submitted_crm_root()
    else:
        root = submitted_crm_root.resolve()
    
    if not root.exists():
        return []
    
    forms = []
    for file_path in sorted(root.glob("*.json"), reverse=True):
        if not file_path.is_file():
            continue
        
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                record = json.load(fh)
        except Exception:
            continue
        
        # Filename format: <username>_<DD.MM.YYYY>_<HH>_<MM>_<SS>
        # Example: demo_04.08.2026_12_30_45
        # Split from the right: last 3 parts are HH, MM, SS; part before is DD.MM.YYYY
        stem = file_path.stem  # strip .json
        parts = stem.rsplit("_", 4)  # max 4 splits from right
        
        if len(parts) >= 5:
            # parts = [username, DD.MM.YYYY, HH, MM, SS]
            username = parts[0]
            date_str = parts[1]   # DD.MM.YYYY
            time_str = f"{parts[2]}:{parts[3]}:{parts[4]}"  # HH:MM:SS
        elif len(parts) == 4:
            # parts = [username_part, DD.MM.YYYY, HH, MM] — fallback
            username = parts[0]
            date_str = parts[1]
            time_str = f"{parts[2]}:{parts[3]}"
        else:
            # Can't parse — use what we have
            username = record.get("username", stem)
            date_str = "—"
            time_str = "—"
        
        # Prefer username stored inside the JSON (more reliable)
        username = record.get("username", username)
        
        # Extract audio filename — from form.audio_filename or metadata.audio_file
        form_section = record.get("form", {})
        metadata_section = record.get("metadata", {})
        audio_filename = (
            form_section.get("audio_filename")
            or metadata_section.get("audio_file")
            or "—"
        )
        
        forms.append({
            "username": username,
            "audio_filename": audio_filename,
            "date": date_str,
            "time": time_str,
            "file_path": str(file_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "form_data": form_section,
        })
    
    return forms


def save_submitted_crm_form(
    username: str,
    form_data: dict,
    submitted_crm_root: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Persist a submitted CRM form as JSON under knowledgebase/submitted_crm_forms.

    Naming convention: <Username>_<DD.MM.YYYY>_<HH_MM_SS>.json
    e.g. alice_14.08.2026_14_00_20.json
    
    JSON structure matches the questionnaire format with questionnaire, metadata, and form fields.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        safe_username = sanitize_username(username)
        logger.info(f"[CRM_SAVE] Starting CRM form save for username={username}, safe_username={safe_username}")
        logger.info(f"[CRM_SAVE] Form data keys: {list(form_data.keys())}")
        
        # Use provided root or resolve from environment/config/default
        if submitted_crm_root is None:
            root = get_submitted_crm_root()
        else:
            root = submitted_crm_root.resolve()
        
        logger.info(f"[CRM_SAVE] Target root directory: {root}")
        logger.info(f"[CRM_SAVE] Root exists before mkdir: {root.exists()}")
        
        root.mkdir(parents=True, exist_ok=True)
        logger.info(f"[CRM_SAVE] Root directory after mkdir: {root.exists()}")

        stamp_dt = now or datetime.now()
        stamp = stamp_dt.strftime("%d.%m.%Y_%H_%M_%S")
        filename = f"{safe_username}_{stamp}.json"
        file_path = root / filename
        logger.info(f"[CRM_SAVE] File path: {file_path}")
        logger.info(f"[CRM_SAVE] File path absolute: {file_path.resolve()}")

        # Map form_data fields to questionnaire structure
        # Handle both database CRM form fields and full questionnaire fields
        questionnaire = {
            "What is the contact method used by Advisee(s)?": form_data.get("encounter_type") or form_data.get("heardFrom", "Not mentioned in transcript."),
            "Heard from the guidance/advice position (if other where?)": form_data.get("heardFrom", "Not mentioned in transcript."),
            "Reason for Immigration": form_data.get("immigrationReason", "Not mentioned in transcript."),
            "Additional Information about the customers": " ".join(form_data.get("additionalInfo", [])) if form_data.get("additionalInfo") else "Not mentioned in transcript.",
            "Education Level": form_data.get("educationLevel", "Not mentioned in transcript."),
            "Customer birth country": form_data.get("birthCountry", "Not mentioned in transcript."),
            "Mother Tongue/Language": form_data.get("motherTongue", "Not mentioned in transcript."),
            "Customer Domicile": form_data.get("domicile", "Not mentioned in transcript."),
            "Position in labour market": " ".join(form_data.get("labourPosition", [])) if form_data.get("labourPosition") else "Not mentioned in transcript.",
            "Duration of residence in Finland": " ".join(form_data.get("residenceDuration", [])) if form_data.get("residenceDuration") else "Not mentioned in transcript.",
            "Contents of the customer visit": " ".join(form_data.get("contents", [])) if form_data.get("contents") else (
                " ".join([str(t) for t in form_data.get("topics_discussed", [])]) if form_data.get("topics_discussed") else "Not mentioned in transcript."
            ),
            "Purpose of visit": " ".join(form_data.get("purpose", [])) if form_data.get("purpose") else "Not mentioned in transcript.",
            "Where the customer is directed": form_data.get("directedTo") or form_data.get("referrals", ["Not mentioned"])[0] if form_data.get("referrals") else "Not mentioned in transcript.",
            "Any Additional Information": form_data.get("additionalInfoText") or form_data.get("notes", ""),
            "Any other Feedback": form_data.get("otherFeedback", ""),
        }

        metadata = {
            "date_time": stamp_dt.strftime("%d/%m/%Y %H:%M"),
            "audio_file": form_data.get("audio_filename", "unknown.wav"),
            "visit_duration": form_data.get("visitDuration", "0 min 0 sec"),
            "audio_duration_sec": 0,
            "segment_count": 0,
            "speakers_detected": [],
            "speaker_roles": {},
            "speaker_durations_sec": {},
            "total_advisor_time_sec": 0,
            "total_advisor_time": "0 min 0 sec",
            "total_customer_time_sec": 0,
            "total_customer_time": "0 min 0 sec",
        }

        # Construct the complete record with questionnaire, metadata, and form
        record = {
            "questionnaire": questionnaire,
            "metadata": metadata,
            "form": form_data,
            "username": safe_username,
            "submitted_at": stamp_dt.isoformat(),
        }

        logger.info(f"[CRM_SAVE] Record created with questionnaire keys: {list(questionnaire.keys())}")
        logger.info(f"[CRM_SAVE] Attempting to write file: {file_path}")
        
        with file_path.open("w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
        
        logger.info(f"[CRM_SAVE] File written successfully: {file_path}")
        logger.info(f"[CRM_SAVE] File exists after write: {file_path.exists()}")
        logger.info(f"[CRM_SAVE] File size: {file_path.stat().st_size} bytes")
        logger.info(f"[CRM_SAVE] SUCCESS: CRM form saved to {file_path}")

        return {
            "filename": filename,
            "path": str(file_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        }
    except Exception as exc:
        logger.error(f"[CRM_SAVE] EXCEPTION during save: {exc}", exc_info=True)
        raise

