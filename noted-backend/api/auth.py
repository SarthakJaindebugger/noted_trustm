import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from services.account_store import ensure_principal_directories, get_admin_accounts, get_user_accounts, principal_id


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedUser:
    id: str
    username: str
    name: str
    role: str


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign_token(unsigned_token: str) -> str:
    signature = hmac.new(
        settings.auth.secret_key.encode("utf-8"),
        unsigned_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def issue_access_token(user: AuthenticatedUser) -> str:
    issued_at = int(time.time())
    payload = {
        "sub": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "iat": issued_at,
        "exp": issued_at + settings.auth.token_ttl_seconds,
    }
    header = {"alg": "HS256", "typ": "NOTED"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    unsigned_token = f"{encoded_header}.{encoded_payload}"
    return f"{unsigned_token}.{_sign_token(unsigned_token)}"


def _decode_access_token(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid token")

    encoded_header, encoded_payload, provided_signature = parts
    unsigned_token = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign_token(unsigned_token)

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature")

    try:
        payload = json.loads(_base64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    expires_at = int(payload.get("exp", 0) or 0)
    if expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")

    return payload


def _authenticated_user_from_account(account: Dict[str, Any], role: str) -> AuthenticatedUser:
    username = str(account.get("username") or "").strip()
    display_name = str(account.get("name") or account.get("display_name") or username)
    account_id = str(account.get("id") or principal_id(role, username))
    ensure_principal_directories(account_id, username, role)
    return AuthenticatedUser(
        id=account_id,
        username=username,
        name=display_name,
        role=role,
    )


def _find_matching_account(accounts, username: str, password: str) -> Optional[Dict[str, Any]]:
    for account in accounts:
        account_username = str(account.get("username") or "")
        account_password = str(account.get("password") or "")
        if hmac.compare_digest(username, account_username) and hmac.compare_digest(password, account_password):
            return account
    return None


def authenticate_credentials(username: str, password: str) -> AuthenticatedUser:
    admin_account = _find_matching_account(get_admin_accounts(), username, password)
    if admin_account:
        return _authenticated_user_from_account(admin_account, "admin")

    user_account = _find_matching_account(get_user_accounts(), username, password)
    if user_account:
        return _authenticated_user_from_account(user_account, "user")

    raise HTTPException(
        status_code=401,
        detail="Invalid credentials",
    )



def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if not settings.auth.enabled:
        return AuthenticatedUser(
            id="anonymous",
            username="anonymous",
            name="Anonymous",
            role=settings.auth.role,
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_access_token(credentials.credentials)
    return AuthenticatedUser(
        id=str(payload.get("sub") or settings.auth.user_id),
        username=str(payload.get("username") or settings.auth.username),
        name=str(payload.get("name") or settings.auth.display_name),
        role=str(payload.get("role") or settings.auth.role),
    )


def require_authenticated_user(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return user


async def require_websocket_auth(websocket: WebSocket) -> AuthenticatedUser:
    if not settings.auth.enabled:
        return AuthenticatedUser(
            id="anonymous",
            username="anonymous",
            name="Anonymous",
            role=settings.auth.role,
        )

    auth_header = websocket.headers.get("authorization", "")
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    if not token:
        token = (
            websocket.query_params.get("access_token")
            or websocket.query_params.get("token")
            or ""
        ).strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    payload = _decode_access_token(token)
    return AuthenticatedUser(
        id=str(payload.get("sub") or settings.auth.user_id),
        username=str(payload.get("username") or settings.auth.username),
        name=str(payload.get("name") or settings.auth.display_name),
        role=str(payload.get("role") or settings.auth.role),
    )
