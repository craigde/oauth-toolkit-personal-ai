#!/usr/bin/env python3
"""
Microsoft OAuth Manager
Handles Microsoft Graph API OAuth tokens (To Do, Calendar, etc.).

Microsoft-specific behaviors:
  - Expiry stored as Unix timestamp float (time.time() + expires_in)
  - Supports both public clients (device code flow) and confidential clients
  - Microsoft often rotates refresh_tokens — new ones must be saved
  - Token endpoint: login.microsoftonline.com/common/oauth2/v2.0/token
  - Validation via Graph API /me/todo/lists endpoint
"""

import time
import requests
from typing import Optional, Callable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from oauth_base import OAuthBase

MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_TODO_LISTS_URL = "https://graph.microsoft.com/v1.0/me/todo/lists"


class MicrosoftOAuth(OAuthBase):
    """Microsoft Graph OAuth token manager (To Do, Calendar)."""

    PROVIDER = "mstodo"

    # ── Token validation ──────────────────────────────────────────────

    def test_token(self, token: Optional[str] = None) -> bool:
        """Test if a Microsoft access token is valid via To Do lists endpoint."""
        if token is None:
            token = self.get_access_token()
        if token is None:
            return False
        return self.test_api_call(MS_TODO_LISTS_URL, token)

    # ── Expiry checking ───────────────────────────────────────────────

    @staticmethod
    def _is_token_fresh(token_data: dict) -> bool:
        """
        Check if the stored token hasn't expired (5-minute buffer).

        Microsoft stores expiry as a Unix timestamp (acquired_at + expires_in
        or a pre-computed expires_at field).
        """
        return token_data.get("expires_at", 0) > time.time() + 300

    def _get_validation_function(self) -> Optional[Callable[[dict], bool]]:
        """Microsoft-specific time-based validation for auto-fallback."""
        return self._is_token_fresh

    # ── Client type detection ─────────────────────────────────────────

    @staticmethod
    def _is_confidential_client(token_data: dict) -> bool:
        """Determine if this token uses a confidential client (has client_secret)."""
        return bool(token_data.get("client_secret"))

    # ── Core refresh logic ────────────────────────────────────────────

    def refresh_token(self, force: bool = False) -> bool:
        """
        Refresh the Microsoft OAuth token if needed.

        Supports both public clients (device code flow, no client_secret)
        and confidential clients (with client_secret). Microsoft may return
        a new refresh_token — if so, it replaces the old one.

        Returns True if a valid token is available after refresh.
        """
        token_data = self.get_token_data()
        if not token_data:
            print("❌ [mstodo] No token data found")
            return False

        if "client_id" not in token_data:
            print("❌ [mstodo] Missing client_id — cannot auto-refresh")
            return False

        current_token = token_data.get("access_token")
        if not current_token:
            print("❌ [mstodo] No access_token in stored data")
            return False

        if not force and self.test_token(current_token) and self._is_token_fresh(token_data):
            print("✅ [mstodo] Token still valid")
            return True

        print("🔄 [mstodo] Refreshing OAuth token...")

        if "refresh_token" not in token_data:
            print("❌ [mstodo] No refresh_token available")
            return False

        refresh_payload = {
            "client_id": token_data["client_id"],
            "refresh_token": token_data["refresh_token"],
            "grant_type": "refresh_token",
        }

        # Confidential clients include client_secret; public clients omit it
        if self._is_confidential_client(token_data):
            refresh_payload["client_secret"] = token_data["client_secret"]

        try:
            response = requests.post(MS_TOKEN_URL, data=refresh_payload, timeout=10)
        except requests.RequestException as e:
            print(f"❌ [mstodo] Network error during refresh: {e}")
            return False

        if response.status_code != 200:
            print(f"❌ [mstodo] Refresh failed (HTTP {response.status_code})")
            if response.status_code == 400:
                print("   Likely cause: refresh token expired or revoked")
            return False

        new_token = response.json()

        # Preserve existing fields (client_id, client_secret, etc.)
        updated = token_data.copy()
        updated["access_token"] = new_token["access_token"]
        updated["expires_at"] = time.time() + new_token["expires_in"]
        # Microsoft may rotate the refresh token
        if "refresh_token" in new_token:
            updated["refresh_token"] = new_token["refresh_token"]

        self.save_token(updated)

        if self.test_token(new_token["access_token"]):
            print("✅ [mstodo] Token refreshed and verified")
            return True
        else:
            print("❌ [mstodo] New token failed verification")
            return False


if __name__ == "__main__":
    oauth = MicrosoftOAuth()
    oauth.refresh_token()
