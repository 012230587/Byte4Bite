"""Short-lived in-process cache for user profiles (reduces repeated DB reads)."""

from __future__ import annotations

import time
from typing import Any, Optional

_PROFILE_TTL_SECONDS = 60
_cache: dict[int, tuple[float, dict[str, Any]]] = {}


def get_cached_profile(user_id: int) -> Optional[dict[str, Any]]:
    entry = _cache.get(user_id)
    if not entry:
        return None
    expires_at, profile = entry
    if time.monotonic() >= expires_at:
        _cache.pop(user_id, None)
        return None
    return profile


def set_cached_profile(user_id: int, profile: dict[str, Any]) -> None:
    _cache[user_id] = (time.monotonic() + _PROFILE_TTL_SECONDS, profile)


def invalidate_profile(user_id: int) -> None:
    _cache.pop(user_id, None)
