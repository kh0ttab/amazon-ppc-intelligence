"""Login with Amazon (LWA) OAuth token management.

Both Amazon Advertising API and SP-API use LWA for authentication.
This module handles token fetching, caching, and refresh.

Credentials needed:
  - client_id       : Your app's Client ID (from developer console)
  - client_secret   : Your app's Client Secret
  - refresh_token   : Long-lived refresh token (from seller authorization flow)

For Amazon Advertising API developer console:
  https://advertising.amazon.com/API/docs/en-us/setting-up/step-2-authentication

For SP-API developer console:
  https://developer.amazonservices.com/
"""

from __future__ import annotations

import time
from typing import Optional
import requests

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

_token_cache: dict[str, dict] = {}  # key -> {access_token, expires_at}


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Get a valid LWA access token, using cache if still valid."""
    cache_key = f"{client_id}:{refresh_token[:8]}"
    cached = _token_cache.get(cache_key)
    if cached and cached["expires_at"] > time.time() + 60:
        return cached["access_token"]

    resp = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _token_cache[cache_key] = {
        "access_token": access_token,
        "expires_at": time.time() + expires_in,
    }
    return access_token


def clear_cache():
    _token_cache.clear()
