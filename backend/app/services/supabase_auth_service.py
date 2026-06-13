from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.app.core.config import Settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


class SupabaseAuthService:
    _CACHE_TTL_SECONDS = 60
    _CACHE_MAX_ITEMS = 512

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: OrderedDict[str, tuple[float, AuthenticatedUser]] = OrderedDict()
        self._cache_lock = Lock()

    def authenticate_authorization_header(
        self,
        authorization: str | None,
    ) -> AuthenticatedUser | None:
        if not authorization:
            return None

        prefix = "Bearer "
        if not authorization.startswith(prefix):
            raise PermissionError("Authorization header must use Bearer token.")

        return self.verify_access_token(authorization[len(prefix) :].strip())

    def verify_access_token(self, access_token: str) -> AuthenticatedUser:
        if not access_token:
            raise PermissionError("Missing Supabase access token.")
        if not self.settings.supabase_auth_configured:
            raise RuntimeError(
                "Supabase Auth is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
                "in the backend .env."
            )

        cached_user = self._get_cached_user(access_token)
        if cached_user is not None:
            return cached_user

        request = Request(
            f"{self.settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": self.settings.supabase_anon_key,
                "Authorization": f"Bearer {access_token}",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError("Invalid or expired Supabase access token.") from exc
            raise RuntimeError("Supabase Auth verification failed.") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("Could not verify Supabase access token.") from exc

        user_id = _first_text(payload.get("id"), payload.get("user") and payload["user"].get("id"))
        if not user_id:
            raise PermissionError("Supabase token did not contain a user id.")

        user = AuthenticatedUser(
            id=user_id,
            email=_first_text(payload.get("email")),
        )
        self._cache_user(access_token, user)
        return user

    def _get_cached_user(self, access_token: str) -> AuthenticatedUser | None:
        cache_key = _token_cache_key(access_token)
        now = monotonic()

        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None

            expires_at, user = cached
            if expires_at <= now:
                self._cache.pop(cache_key, None)
                return None

            self._cache.move_to_end(cache_key)
            return user

    def _cache_user(self, access_token: str, user: AuthenticatedUser) -> None:
        cache_key = _token_cache_key(access_token)
        expires_at = monotonic() + self._CACHE_TTL_SECONDS

        with self._cache_lock:
            self._cache[cache_key] = (expires_at, user)
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._CACHE_MAX_ITEMS:
                self._cache.popitem(last=False)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _token_cache_key(access_token: str) -> str:
    return sha256(access_token.encode("utf-8")).hexdigest()
