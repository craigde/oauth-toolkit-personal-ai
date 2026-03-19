#!/usr/bin/env python3
"""
Google OAuth Provider
Handles Gmail + Calendar OAuth tokens with Google-specific patterns.

Google-specific behaviors:
  - Expiry stored as ISO 8601 UTC string (e.g. "2025-03-04T18:30:00+00:00")
  - Token endpoint from stored token data (token_uri field)
  - Refresh uses standard OAuth2 client_id/client_secret/refresh_token
  - Validation via oauth2/v1/tokeninfo endpoint
"""

import json
import logging
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

from oauth_base import OAuthBase

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v1/tokeninfo"


class GoogleOAuth(OAuthBase):
    """Google OAuth token manager (Gmail + Calendar scopes)."""

    PROVIDER = "google"

    # Google OAuth configuration - credentials stored WITH tokens (Pearl's approach)
    @property
    def CLIENT_ID(self):
        """Get client_id from the same token data (stored together, cached)."""
        cached = getattr(self, "_cached_client_id", None)
        if cached is not None:
            return cached
        token_data = self.get_token_data()
        value = token_data.get("client_id", "") if token_data else ""
        if value:
            self._cached_client_id = value
        return value

    @property
    def CLIENT_SECRET(self):
        """Get client_secret from the same token data (stored together, cached)."""
        cached = getattr(self, "_cached_client_secret", None)
        if cached is not None:
            return cached
        token_data = self.get_token_data()
        value = token_data.get("client_secret", "") if token_data else ""
        if value:
            self._cached_client_secret = value
        return value
    REDIRECT_URI = "http://localhost:8080/"
    SCOPES = ["https://www.googleapis.com/auth/calendar", 
              "https://www.googleapis.com/auth/gmail.modify"]

    # ── Token validation ──────────────────────────────────────────────

    def test_token(self, token: Optional[str] = None) -> bool:
        """Test if a Google access token is valid via tokeninfo endpoint."""
        if token is None:
            token = self.get_access_token()
        if token is None:
            return False
        try:
            response = requests.get(
                GOOGLE_TOKENINFO_URL,
                params={"access_token": token},
                timeout=10,
            )
            return 200 <= response.status_code < 300
        except requests.RequestException:
            return False

    # ── Expiry helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_expiry(expiry_str: str) -> Optional[float]:
        """Parse a Google ISO expiry string into a Unix timestamp."""
        try:
            # Normalize timezone format
            normalized = expiry_str.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _make_expiry(expires_in_seconds: int) -> str:
        """Create an ISO 8601 UTC expiry string from expires_in value."""
        expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        return expiry_dt.isoformat()

    def _is_token_fresh(self, token_data: dict) -> bool:
        """Check if the stored token is still valid (5-minute buffer)."""
        expiry_str = token_data.get("expiry")
        if not expiry_str:
            return False
        expiry_ts = self._parse_expiry(expiry_str)
        if expiry_ts is None:
            return False
        return expiry_ts > time.time() + 300  # 5-minute buffer

    def _get_validation_function(self) -> Optional[Callable[[dict], bool]]:
        """Google-specific time-based validation for auto-fallback."""
        return self._is_token_fresh

    # ── Token field migration ─────────────────────────────────────────

    @staticmethod
    def _normalize_token_fields(token_data: dict) -> dict:
        """Migrate legacy 'token' field → 'access_token'."""
        if "token" in token_data and "access_token" not in token_data:
            token_data["access_token"] = token_data.pop("token")
        return token_data

    # ── Token refresh ─────────────────────────────────────────────────

    def refresh_token(self, force: bool = False) -> bool:
        """
        Refresh Google access token using the refresh token.
        
        Args:
            force: If True, refresh even if current token appears valid
            
        Returns:
            True if refresh successful, False otherwise
        """
        try:
            # Get current token data
            current_data = self.get_token_data()
            if current_data is None:
                logger.error("[%s] No existing token data for refresh", self.PROVIDER)
                return False

            # Check if refresh is needed (unless forced)
            if not force and self._is_token_fresh(current_data):
                logger.info("[%s] Token still fresh, skipping refresh", self.PROVIDER)
                return True

            refresh_token = current_data.get("refresh_token")
            if not refresh_token:
                logger.error("[%s] No refresh token available", self.PROVIDER)
                return False

            # Get token endpoint
            token_uri = current_data.get("token_uri", "https://oauth2.googleapis.com/token")

            # Prepare refresh request
            refresh_data = {
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }

            # Make refresh request
            response = requests.post(token_uri, data=refresh_data, timeout=30)

            if response.status_code != 200:
                logger.error("[%s] Token refresh failed: %s", self.PROVIDER, response.status_code)
                logger.error("   Response: %s", response.text)
                return False

            # Parse response
            try:
                new_token_data = response.json()
            except (ValueError, json.JSONDecodeError):
                logger.error("[%s] Invalid JSON in refresh response", self.PROVIDER)
                return False

            if "access_token" not in new_token_data:
                logger.error("[%s] No access_token in refresh response", self.PROVIDER)
                return False

            # Preserve fields from original token
            updated_data = current_data.copy()
            updated_data["access_token"] = new_token_data["access_token"]

            # Update expiry
            if "expires_in" in new_token_data:
                updated_data["expiry"] = self._make_expiry(new_token_data["expires_in"])

            # Update refresh token if provided
            if "refresh_token" in new_token_data:
                updated_data["refresh_token"] = new_token_data["refresh_token"]

            # Save updated token
            self.save_token(updated_data)
            logger.info("[%s] Token refreshed successfully", self.PROVIDER)
            return True

        except requests.RequestException as e:
            logger.error("[%s] Network error during refresh: %s", self.PROVIDER, e)
            return False
        except (KeyError, ValueError, TypeError) as e:
            logger.error("[%s] Unexpected error during refresh: %s", self.PROVIDER, e)
            return False


# ── Standalone utilities ──────────────────────────────────────────────

def get_authorization_url(client_id: str) -> str:
    """
    Generate the Google OAuth authorization URL.

    Args:
        client_id: Google OAuth client ID

    Returns:
        URL to redirect user to for authorization
    """
    from urllib.parse import urlencode

    auth_params = {
        'client_id': client_id,
        'redirect_uri': GoogleOAuth.REDIRECT_URI,
        'scope': ' '.join(GoogleOAuth.SCOPES),
        'response_type': 'code',
        'access_type': 'offline',
        'prompt': 'consent'  # Force consent to ensure refresh token
    }

    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(auth_params)}"


def exchange_authorization_code(auth_code: str, client_id: str, client_secret: str) -> dict:
    """
    Exchange authorization code for tokens.

    Args:
        auth_code: Authorization code from OAuth callback
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret

    Returns:
        Token data dictionary
    """
    token_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': GoogleOAuth.REDIRECT_URI
    }

    response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
    response.raise_for_status()

    try:
        token_response = response.json()
    except (ValueError, json.JSONDecodeError):
        raise ValueError("Invalid JSON in token exchange response")

    if 'access_token' not in token_response:
        raise KeyError("No access_token in token exchange response")

    # Add expiry timestamp
    if 'expires_in' in token_response:
        expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=token_response['expires_in'])
        token_response['expiry'] = expiry_dt.isoformat()

    return token_response


if __name__ == "__main__":
    print("Google OAuth Provider")
    print("====================")
    print(f"Scopes: {', '.join(GoogleOAuth.SCOPES)}")
    print()
    print("Setup steps:")
    print("1. Create Google Cloud project")
    print("2. Enable Calendar and Gmail APIs")
    print("3. Create OAuth 2.0 credentials")
    print("4. Store client_id and client_secret in 1Password with token data")
    print("5. Run initial authorization flow")
    print()
    google = GoogleOAuth()
    client_id = google.CLIENT_ID
    if client_id:
        print("Authorization URL:")
        print(get_authorization_url(client_id))
    else:
        print("No client_id found. Store credentials in 1Password first.")