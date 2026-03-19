"""
OAuth Providers

Each provider implements the OAuthBase interface with provider-specific
token refresh, validation, and expiry handling.

Available providers:
  - GoogleOAuth: Google Calendar, Gmail (ISO 8601 expiry)
  - MicrosoftOAuth: Microsoft Graph / To Do (Unix timestamp expiry, public + confidential clients)
  - SpotifyOAuth: Spotify Web API (Basic auth refresh, optional refresh token rotation)
"""

from .google_oauth import GoogleOAuth
from .microsoft_oauth import MicrosoftOAuth
from .spotify_oauth import SpotifyOAuth

__all__ = ["GoogleOAuth", "MicrosoftOAuth", "SpotifyOAuth"]
