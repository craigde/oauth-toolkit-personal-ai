#!/usr/bin/env python3
"""
Spotify OAuth Manager
Handles Spotify Web API OAuth tokens.

Spotify-specific behaviors:
  - Refresh uses Basic auth header: base64(client_id:client_secret)
  - Expiry stored as Unix timestamp float (time.time() + expires_in)
  - Spotify does NOT always return a new refresh_token — only save if present
  - Token endpoint: accounts.spotify.com/api/token
  - Validation via /v1/me endpoint
"""

import time
import base64
import requests
from typing import Optional, Callable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from oauth_base import OAuthBase

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_ME_URL = "https://api.spotify.com/v1/me"


class SpotifyOAuth(OAuthBase):
    """Spotify Web API OAuth token manager."""

    PROVIDER = "spotify"

    # ── Token validation ──────────────────────────────────────────────

    def test_token(self, token: Optional[str] = None) -> bool:
        """Test if a Spotify access token is valid via /v1/me endpoint."""
        if token is None:
            token = self.get_access_token()
        if token is None:
            return False
        return self.test_api_call(SPOTIFY_ME_URL, token)

    # ── Expiry checking ───────────────────────────────────────────────

    @staticmethod
    def _is_token_fresh(token_data: dict) -> bool:
        """
        Check if the stored token hasn't expired (5-minute buffer).

        Spotify stores expiry as a Unix timestamp (time.time() + expires_in).
        """
        return token_data.get("expires_at", 0) > time.time() + 300

    def _get_validation_function(self) -> Optional[Callable[[dict], bool]]:
        """Spotify-specific time-based validation for auto-fallback."""
        return self._is_token_fresh

    # ── Auth helpers ──────────────────────────────────────────────────

    @staticmethod
    def _make_basic_auth(client_id: str, client_secret: str) -> str:
        """
        Build Basic auth header for Spotify's token endpoint.

        Spotify requires client credentials as a Base64-encoded
        "client_id:client_secret" string in the Authorization header.
        """
        credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(credentials.encode("ascii")).decode("ascii")
        return f"Basic {encoded}"

    # ── Core refresh logic ────────────────────────────────────────────

    def refresh_token(self, force: bool = False) -> bool:
        """
        Refresh the Spotify OAuth token if needed.

        Spotify uses Basic auth (base64 client_id:client_secret) for refresh
        requests, unlike most providers that pass credentials in the body.
        Spotify may or may not return a new refresh_token — only update if present.

        Returns True if a valid token is available after refresh.
        """
        token_data = self.get_token_data()
        if not token_data:
            print("❌ [spotify] No token data found")
            return False

        for required in ("client_id", "client_secret"):
            if required not in token_data:
                print(f"❌ [spotify] Missing {required} — cannot auto-refresh")
                return False

        current_token = token_data.get("access_token")
        if not current_token:
            print("❌ [spotify] No access_token in stored data")
            return False

        if not force and self.test_token(current_token) and self._is_token_fresh(token_data):
            print("✅ [spotify] Token still valid")
            return True

        print("🔄 [spotify] Refreshing OAuth token...")

        if "refresh_token" not in token_data:
            print("❌ [spotify] No refresh_token available")
            return False

        try:
            response = requests.post(
                SPOTIFY_TOKEN_URL,
                headers={
                    "Authorization": self._make_basic_auth(
                        token_data["client_id"], token_data["client_secret"]
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token_data["refresh_token"],
                },
                timeout=10,
            )
        except requests.RequestException as e:
            print(f"❌ [spotify] Network error during refresh: {e}")
            return False

        if response.status_code != 200:
            print(f"❌ [spotify] Refresh failed (HTTP {response.status_code})")
            if response.status_code == 400:
                print("   Likely cause: refresh token expired or revoked")
            return False

        new_token = response.json()

        # Preserve existing fields (client_id, client_secret, etc.)
        updated = token_data.copy()
        updated["access_token"] = new_token["access_token"]
        updated["expires_at"] = time.time() + new_token["expires_in"]
        # Spotify may or may not rotate the refresh token
        if "refresh_token" in new_token:
            updated["refresh_token"] = new_token["refresh_token"]

        self.save_token(updated)

        if self.test_token(new_token["access_token"]):
            print("✅ [spotify] Token refreshed and verified")
            return True
        else:
            print("❌ [spotify] New token failed verification")
            return False


if __name__ == "__main__":
    oauth = SpotifyOAuth()
    oauth.refresh_token()
