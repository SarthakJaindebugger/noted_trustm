import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings

logger = logging.getLogger(__name__)


def sanitize_path_segment(value: str) -> str:
    """Return a filesystem-safe directory name for an account identifier."""
    safe_value = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in value.strip())
    return safe_value or "unknown"


def _read_account_file(path: str) -> List[Dict[str, Any]]:
    account_path = Path(path)
    if not account_path.is_absolute():
        backend_root = Path(__file__).resolve().parents[1]
        account_path = backend_root / account_path
        if not account_path.exists():
            repo_root = backend_root.parent
            account_path = repo_root / path

    if not account_path.exists():
        logger.warning("Account file does not exist: %s", account_path)
        return []

    with account_path.open("r", encoding="utf-8") as file_obj:
        raw = json.load(file_obj)

    if isinstance(raw, dict):
        accounts = raw.get("accounts", [])
    else:
        accounts = raw

    if not isinstance(accounts, list):
        logger.warning("Account file %s must contain a list or an accounts list", account_path)
        return []

    valid_accounts = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        username = str(account.get("username") or "").strip()
        password = str(account.get("password") or "")
        if not username or not password:
            logger.warning("Skipping account without username or password in %s", account_path)
            continue
        valid_accounts.append(account)
    return valid_accounts


def _legacy_account(username: str, password: str, display_name: str, role: str) -> Dict[str, Any]:
    return {
        "username": username,
        "password": password,
        "name": display_name,
        "role": role,
    }


def _merge_accounts(file_accounts: Iterable[Dict[str, Any]], legacy_accounts: Iterable[Dict[str, Any]], role: str):
    accounts_by_username: Dict[str, Dict[str, Any]] = {}
    for account in file_accounts:
        username = str(account.get("username") or "").strip()
        if username:
            accounts_by_username[username] = {**account, "role": role}
    for account in legacy_accounts:
        username = str(account.get("username") or "").strip()
        if username and username not in accounts_by_username:
            accounts_by_username[username] = {**account, "role": role}
    return list(accounts_by_username.values())


def get_user_accounts() -> List[Dict[str, Any]]:
    return _read_account_file(settings.auth.users_file)


def get_admin_accounts() -> List[Dict[str, Any]]:
    return _read_account_file(settings.auth.admins_file)


def get_all_accounts() -> List[Dict[str, Any]]:
    return [*get_user_accounts(), *get_admin_accounts()]


def principal_id(role: str, username: str) -> str:
    return f"{role}:{username}"


def _backend_relative_path(path: str) -> str:
    resolved_path = Path(path)
    if resolved_path.is_absolute():
        return str(resolved_path)

    backend_root = Path(__file__).resolve().parents[1]
    candidate = backend_root / resolved_path
    if candidate.exists():
        return str(candidate)

    repo_root = backend_root.parent
    fallback_candidate = repo_root / resolved_path
    if fallback_candidate.exists():
        return str(fallback_candidate)

    # Last resort: preserve backend-relative path for container deployments.
    return str(candidate)


def principal_data_dir(role: str, username: str) -> str:
    return os.path.join(
        _backend_relative_path(settings.storage.data_dir),
        f"{role}s",
        sanitize_path_segment(username),
    )


def principal_data_dir_from_id(account_id: Optional[str], username: Optional[str] = None, role: Optional[str] = None) -> str:
    resolved_role = role or "user"
    resolved_username = username or "unknown"
    if account_id and ":" in account_id:
        maybe_role, maybe_username = account_id.split(":", 1)
        resolved_role = maybe_role or resolved_role
        resolved_username = maybe_username or resolved_username
    return principal_data_dir(resolved_role, resolved_username)


def recordings_dir_for_principal(account_id: Optional[str], username: Optional[str] = None, role: Optional[str] = None) -> str:
    return os.path.join(principal_data_dir_from_id(account_id, username=username, role=role), settings.storage.recordings_dir)


def uploads_dir_for_principal(account_id: Optional[str], username: Optional[str] = None, role: Optional[str] = None) -> str:
    return os.path.join(principal_data_dir_from_id(account_id, username=username, role=role), settings.storage.upload_dir)


def ensure_principal_directories(account_id: str, username: str, role: str) -> Dict[str, str]:
    base_dir = principal_data_dir(role, username)
    uploads_dir = os.path.join(base_dir, settings.storage.upload_dir)
    recordings_dir = os.path.join(base_dir, settings.storage.recordings_dir)
    for directory in (base_dir, uploads_dir, recordings_dir):
        os.makedirs(directory, exist_ok=True)
    return {
        "base_dir": base_dir,
        "uploads_dir": uploads_dir,
        "recordings_dir": recordings_dir,
    }


def ensure_all_account_directories() -> None:
    for account in get_all_accounts():
        username = str(account.get("username") or "").strip()
        role = str(account.get("role") or "user").strip() or "user"
        if username:
            ensure_principal_directories(principal_id(role, username), username, role)
