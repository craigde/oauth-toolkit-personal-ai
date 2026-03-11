#!/usr/bin/env python3
"""
Template OAuth Provider
Use this as a starting point for implementing new OAuth providers.

Steps to create a new provider:
1. Copy this file to {provider}_oauth.py
2. Update the PROVIDER name and configuration
3. Implement refresh_token() method
4. Add provider-specific validation if needed
5. Add to PROVIDER_CONFIG in oauth_base.py
"""

import time
import requests
from typing import Optional, Callable

from oauth_base import OAuthBase


class TemplateOAuth(OAuthBase):
    """Template OAuth provider implementation."""

    # Set the provider name (must match PROVIDER_CONFIG key)
    PROVIDER = "template"

    # OAuth configuration - credentials stored WITH tokens (Pearl's approach)
    @property
    def CLIENT_ID(self):
        """Get client_id from the same token data (stored together)."""
        token_data = self.get_token_data()
        return token_data.get("client_id", "") if token_data else ""
    
    @property  
    def CLIENT_SECRET(self):
        """Get client_secret from the same token data (stored together)."""
        token_data = self.get_token_data()
        return token_data.get("client_secret", "") if token_data else ""
    REDIRECT_URI = "http://localhost:8080/"
    TOKEN_URL = "https://api.example.com/oauth/token"
    AUTH_URL = "https://api.example.com/oauth/authorize"
    SCOPES = ["read", "write"]

    # ── Token validation ──────────────────────────────────────────────

    def test_token(self, token: Optional[str] = None) -> bool:
        """Test if a token is valid for this provider."""
        if token is None:
            token = self.get_access_token()
        if token is None:
            return False
        
        # Replace with your provider's token validation endpoint
        validation_url = "https://api.example.com/user"
        return self.test_api_call(validation_url, token)

    # ── Token freshness (optional) ────────────────────────────────────

    def _is_token_fresh(self, token_data: dict) -> bool:
        """
        Check if the stored token is still valid.
        
        Implement this if your provider includes expiry information.
        Common patterns:
        - Unix timestamp: expires_at > time.time()
        - ISO string: parse and compare to current time
        - Expires-in: acquired_at + expires_in > time.time()
        """
        # Example for expires_at Unix timestamp
        expires_at = token_data.get("expires_at")
        if expires_at:
            return expires_at > time.time() + 300  # 5-minute buffer
        
        # Example for expires_in + acquired_at pattern
        acquired_at = token_data.get("acquired_at", 0)
        expires_in = token_data.get("expires_in", 0)
        if acquired_at and expires_in:
            return (acquired_at + expires_in) > time.time() + 300
        
        # If no expiry info, assume token might be stale
        return False

    def _get_validation_function(self) -> Optional[Callable[[dict], bool]]:
        """Return validation function for auto-fallback logic."""
        return self._is_token_fresh

    # ── Token field normalization (optional) ──────────────────────────

    @staticmethod
    def _normalize_token_fields(token_data: dict) -> dict:
        """
        Normalize token field names for this provider.
        
        Handle provider-specific field naming differences.
        Examples:
        - Some use 'token', others 'access_token'
        - Some use 'expire_time', others 'expires_at'
        """
        # Example: migrate 'token' to 'access_token'
        if "token" in token_data and "access_token" not in token_data:
            token_data["access_token"] = token_data.pop("token")
        
        # Example: ensure consistent timestamp format
        if "expire_time" in token_data and "expires_at" not in token_data:
            token_data["expires_at"] = token_data.pop("expire_time")
        
        return token_data

    # ── Token refresh (required) ───────────────────────────────────────

    def refresh_token(self, force: bool = False) -> bool:
        """
        Refresh access token using the refresh token.
        
        This is the main method you need to implement for your provider.
        
        Args:
            force: If True, refresh even if current token appears valid
            
        Returns:
            True if refresh successful, False otherwise
        """
        try:
            # Get current token data
            current_data = self.get_token_data()
            if current_data is None:
                print(f"❌ [{self.PROVIDER}] No existing token data for refresh")
                return False

            # Check if refresh is needed (unless forced)
            if not force and self._is_token_fresh(current_data):
                print(f"✅ [{self.PROVIDER}] Token still fresh, skipping refresh")
                return True

            # Get refresh token
            refresh_token = current_data.get("refresh_token")
            if not refresh_token:
                print(f"❌ [{self.PROVIDER}] No refresh token available")
                return False

            # Prepare refresh request
            refresh_data = {
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
            
            # Some providers need scope in refresh
            if hasattr(self, 'SCOPES') and self.SCOPES:
                refresh_data["scope"] = " ".join(self.SCOPES)

            # Make refresh request
            response = requests.post(self.TOKEN_URL, data=refresh_data, timeout=30)
            
            if response.status_code != 200:
                print(f"❌ [{self.PROVIDER}] Token refresh failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

            # Parse response
            new_token_data = response.json()
            
            # Update token data
            updated_data = current_data.copy()
            updated_data["access_token"] = new_token_data["access_token"]
            
            # Update expiry if provided
            if "expires_in" in new_token_data:
                # Convert expires_in to absolute timestamp
                updated_data["expires_at"] = time.time() + new_token_data["expires_in"]
            
            # Update refresh token if provided (not all providers do this)
            if "refresh_token" in new_token_data:
                updated_data["refresh_token"] = new_token_data["refresh_token"]

            # Save updated token
            self.save_token(updated_data)
            print(f"✅ [{self.PROVIDER}] Token refreshed successfully")
            return True

        except requests.RequestException as e:
            print(f"❌ [{self.PROVIDER}] Network error during refresh: {e}")
            return False
        except Exception as e:
            print(f"❌ [{self.PROVIDER}] Unexpected error during refresh: {e}")
            return False


# ── Initial authorization flow ────────────────────────────────────────

def get_authorization_url() -> str:
    """
    Generate the OAuth authorization URL for initial setup.
    
    Returns:
        URL to redirect user to for authorization
    """
    from urllib.parse import urlencode
    
    auth_params = {
        'client_id': TemplateOAuth.CLIENT_ID,
        'redirect_uri': TemplateOAuth.REDIRECT_URI,
        'scope': ' '.join(TemplateOAuth.SCOPES),
        'response_type': 'code',
        'access_type': 'offline',  # Request refresh token
        # Add provider-specific parameters here
    }
    
    return f"{TemplateOAuth.AUTH_URL}?{urlencode(auth_params)}"


def exchange_authorization_code(auth_code: str) -> dict:
    """
    Exchange authorization code for initial tokens.
    
    Args:
        auth_code: Authorization code from OAuth callback
        
    Returns:
        Token data dictionary
    """
    token_data = {
        'client_id': TemplateOAuth.CLIENT_ID,
        'client_secret': TemplateOAuth.CLIENT_SECRET,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': TemplateOAuth.REDIRECT_URI
    }
    
    response = requests.post(TemplateOAuth.TOKEN_URL, data=token_data)
    response.raise_for_status()
    
    token_response = response.json()
    
    # Add absolute expiry timestamp
    if 'expires_in' in token_response:
        token_response['expires_at'] = time.time() + token_response['expires_in']
    
    return token_response


if __name__ == "__main__":
    print("Template OAuth Provider")
    print("======================")
    print("This is a template for creating new OAuth providers.")
    print()
    print("Steps to customize:")
    print("1. Update PROVIDER name")
    print("2. Set CLIENT_ID, CLIENT_SECRET, URLs")
    print("3. Implement provider-specific refresh logic")
    print("4. Add to PROVIDER_CONFIG in oauth_base.py")
    print("5. Test with your provider's API")
    print()
    print("Authorization URL:")
    print(get_authorization_url())