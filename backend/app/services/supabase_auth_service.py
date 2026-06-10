from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.app.core.config import Settings


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


class SupabaseAuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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

        return AuthenticatedUser(
            id=user_id,
            email=_first_text(payload.get("email")),
        )


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
