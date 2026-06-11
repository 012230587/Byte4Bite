"""Shared FastAPI dependencies for authentication."""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from services.auth_service import decode_token


def _token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return token or None


def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    token = _token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return int(payload["sub"])


def get_optional_user_id(authorization: Optional[str] = Header(None)) -> Optional[int]:
    token = _token_from_header(authorization)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        return None
