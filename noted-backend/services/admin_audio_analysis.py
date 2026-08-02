from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from speech_analysis_qa.utils import sanitize_username

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_USERS_ROOT = REPO_ROOT / "knowledgebase" / "users_admin_data" / "users"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


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


def build_analysis_output_paths(audio_path: str | Path, users_root: Optional[Path] = None, now: Optional[datetime] = None) -> tuple[Path, Path, Path, str]:
    users_root = (users_root or get_default_users_root()).resolve()
    resolved_audio = resolve_audio_path(audio_path)
    username = infer_username(resolved_audio, users_root)
    if not username:
        raise ValueError("Selected audio file is not under the configured users directory")

    user_root = users_root / sanitize_username(username)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", resolved_audio.stem).strip("._-") or "audio"
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")

    target_dir = user_root / "uploads" / f"{safe_stem}_{stamp}"
    embedding_dir = user_root / "embedding" / f"{safe_stem}_{stamp}"
    pipeline_parent_dir = target_dir.parent
    return target_dir, embedding_dir, pipeline_parent_dir, username


def analyze_audio_file(audio_path: str | Path, users_root: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    target_dir, embedding_dir, pipeline_parent_dir, username = build_analysis_output_paths(audio_path, users_root, now)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    embedding_dir.mkdir(parents=True, exist_ok=True)

    resolved_audio = resolve_audio_path(audio_path)
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
