#!/usr/bin/env python3
"""
OAuth Base Library
Shared infrastructure for all OAuth providers.

Token storage (two tiers):
  1. tmpfs    — /dev/shm/oauth-token-{provider}.json  (~3ms, RAM-only, per-provider file)
  2. 1Password — encrypted vault                       (~1200ms, durable across reboots)

Read order:  tmpfs → 1Password (backfills tmpfs on cold-storage hit)
Write order: tmpfs first (instant), then 1Password (durable backup)

Security model:
  - tmpfs is RAM-backed (/dev/shm) — never touches disk, vanishes on reboot
  - Per-provider files — no shared state, no file locking, no race conditions
  - File permissions: 600 owner-only
  - 1Password remains the durable encrypted backup for reboot recovery
"""

import os
import json
import logging
import stat
import subprocess
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────
# Set your 1Password vault name here
VAULT = os.getenv("OAUTH_1PASSWORD_VAULT", "Personal")
TMPFS_DIR = Path("/dev/shm")

# Provider registry — maps provider key to 1Password item name
# Customize these item names to match your 1Password setup
PROVIDER_CONFIG: Dict[str, Dict[str, str]] = {
    "google": {"item_name": "Google OAuth Token"},
    "microsoft": {"item_name": "Microsoft OAuth Token"},
    "spotify": {"item_name": "Spotify OAuth Token"},
    # Add your providers here
}


class OAuthBase:
    """
    Shared infrastructure for OAuth token management.

    Subclasses MUST:
    1. Set PROVIDER = "google"  # key into PROVIDER_CONFIG
    2. Implement refresh_token(force: bool = False) -> bool
    
    Optional overrides:
    - _get_validation_function() for provider-specific token validation
    - _normalize_token_fields() for provider-specific field mapping
    """

    PROVIDER: str = ""

    def __init__(self):
        if self.PROVIDER not in PROVIDER_CONFIG:
            raise ValueError(
                f"Unknown provider {self.PROVIDER!r}. "
                f"Valid: {list(PROVIDER_CONFIG.keys())}"
            )
        self._config = PROVIDER_CONFIG[self.PROVIDER]

    # ── Tier 1: tmpfs warm cache ──────────────────────────────────────
    #
    # Each provider gets its own file: /dev/shm/oauth-token-{provider}.json
    # No shared state → no file locking needed → no race conditions.

    def _tmpfs_path(self) -> Path:
        """Return the per-provider tmpfs file path."""
        return TMPFS_DIR / f"oauth-token-{self.PROVIDER}.json"

    def _read_from_tmpfs(self) -> Optional[dict]:
        """Read this provider's token from its dedicated tmpfs file."""
        path = self._tmpfs_path()
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _write_to_tmpfs(self, token_data: dict) -> None:
        """Write this provider's token to its dedicated tmpfs file."""
        path = self._tmpfs_path()
        try:
            path.write_text(json.dumps(token_data))
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
        except OSError as e:
            logger.warning("[%s] tmpfs write failed: %s", self.PROVIDER, e)

    # ── Tier 2: 1Password cold storage ────────────────────────────────

    @staticmethod
    def _parse_1password_json(raw: str) -> dict:
        """
        Parse JSON from 1Password CLI output.
        
        The CLI sometimes wraps values in outer double-quotes with
        inner quotes doubled (""{""key"":""val""}"").
        """
        raw = raw.strip()
        
        # Handle 1Password CLI quote-doubling
        if raw.startswith('""') and raw.endswith('""'):
            raw = raw[2:-2].replace('""', '"')
        
        return json.loads(raw)

    def _read_from_1password(self) -> Optional[dict]:
        """Read this provider's token from 1Password vault."""
        item_name = self._config["item_name"]
        
        try:
            result = subprocess.run(
                ["op", "item", "get", item_name, "--vault", VAULT, "--fields", "token_json", "--reveal"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error("[%s] 1Password read failed: %s", self.PROVIDER, result.stderr)
                return None

            token_data = self._parse_1password_json(result.stdout)
            return token_data
            
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("[%s] 1Password CLI error: %s", self.PROVIDER, e)
            return None
        except json.JSONDecodeError as e:
            logger.error("[%s] Invalid JSON from 1Password: %s", self.PROVIDER, e)
            return None

    def _write_to_1password(self, token_data: Dict[str, Any]) -> bool:
        """Write this provider's token to 1Password vault."""
        item_name = self._config["item_name"]
        json_str = json.dumps(token_data)
        
        try:
            result = subprocess.run(
                ["op", "item", "edit", item_name, "--vault", VAULT, f"token_json={json_str}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True
            else:
                logger.error("[%s] 1Password write failed: %s", self.PROVIDER, result.stderr)
                return False

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("[%s] 1Password CLI error: %s", self.PROVIDER, e)
            return False

    # ── Token retrieval with auto-fallback ───────────────────────────

    def get_token_data(self, validate_fn: Optional[Callable[[dict], bool]] = None) -> Optional[dict]:
        """
        Get the full token dict for this provider.

        Resolution order:
          1. tmpfs     → sub-millisecond, per-provider file
          2. 1Password → slow but always correct, backfills tmpfs

        Args:
            validate_fn: Optional function that takes token_data and returns
                        True if still valid, False if stale. When provided,
                        a stale tmpfs token triggers fallback to 1Password.
        """
        # ── Tier 1: tmpfs (fast path) ──────────────────────────────────
        tmpfs_data = self._read_from_tmpfs()
        if tmpfs_data:
            # Apply provider-specific normalization
            tmpfs_data = self._normalize_token_fields(tmpfs_data)
            
            if validate_fn and not validate_fn(tmpfs_data):
                logger.warning("[%s] tmpfs token stale, falling back to 1Password", self.PROVIDER)
            else:
                return tmpfs_data

        # ── Tier 2: 1Password (slow, authoritative) ────────────────────
        logger.info("[%s] Reading from 1Password...", self.PROVIDER)
        op_data = self._read_from_1password()
        if op_data:
            # Apply provider-specific normalization
            op_data = self._normalize_token_fields(op_data)
            self._write_to_tmpfs(op_data)
            logger.info("[%s] Backfilled tmpfs from 1Password", self.PROVIDER)
        return op_data

    def get_access_token(self) -> Optional[str]:
        """
        Return just the access_token string.
        
        Uses provider-specific validation to detect stale tokens and
        automatically falls through to 1Password if needed.
        """
        validate_fn = self._get_validation_function()
        data = self.get_token_data(validate_fn=validate_fn)
        if data is None:
            return None
        return data.get("access_token")

    # ── Token persistence ─────────────────────────────────────────────

    def save_token(self, token_data: Dict[str, Any]) -> None:
        """
        Persist updated token data to both storage tiers.
        
        tmpfs is written first so other processes see the update immediately,
        even before the 1Password write completes.
        """
        # Apply provider-specific normalization
        token_data = self._normalize_token_fields(token_data)
        
        self._write_to_tmpfs(token_data)

        if self._write_to_1password(token_data):
            logger.info("[%s] Token saved to tmpfs + 1Password", self.PROVIDER)
        else:
            logger.warning("[%s] Token saved to tmpfs only (1Password write failed)", self.PROVIDER)

    # ── API testing ───────────────────────────────────────────────────

    @staticmethod
    def test_api_call(url: str, token: str, timeout: int = 10) -> bool:
        """
        Test whether a Bearer token is accepted by an API endpoint.
        
        Returns True if the API accepts the token (2xx response),
        False otherwise.
        """
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers, timeout=timeout)
            return 200 <= response.status_code < 300
        except requests.RequestException:
            return False

    # ── Provider-specific hooks (override in subclasses) ──────────────

    def _get_validation_function(self) -> Optional[Callable[[dict], bool]]:
        """
        Return a function to validate token freshness for this provider.
        
        Should return a function that takes token_data dict and returns:
        - True if token is still valid/fresh
        - False if token is stale/expired
        
        Used by auto-fallback logic to decide when to bypass tmpfs cache.
        """
        return None

    @staticmethod
    def _normalize_token_fields(token_data: dict) -> dict:
        """
        Normalize token field names for this provider.
        
        Override in subclasses to handle provider-specific field mapping.
        For example, some providers use 'token', others 'access_token'.
        """
        return token_data

    # ── Abstract methods (implement in subclasses) ────────────────────

    def refresh_token(self, force: bool = False) -> bool:
        """
        Refresh the access token using the refresh token.
        
        Args:
            force: If True, refresh even if current token appears valid
            
        Returns:
            True if refresh successful, False otherwise
            
        Should call save_token() with the new token data if successful.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement refresh_token()")

    # ── Testing and validation ────────────────────────────────────────

    def test_token(self, token: Optional[str] = None) -> bool:
        """Test if a token is valid for this provider. Override in subclasses."""
        if token is None:
            token = self.get_access_token()
        if token is None:
            return False
        # Subclasses should override with provider-specific validation URL
        return True


# ── Standalone utilities ──────────────────────────────────────────────

def seed_tmpfs_from_1password() -> None:
    """
    Load all provider tokens from 1Password into tmpfs.
    
    Called once at startup to warm the tmpfs cache.
    """
    logger.info("Seeding tmpfs cache from 1Password...")

    for provider_key in PROVIDER_CONFIG.keys():
        try:
            # Dynamically import the provider class
            module_name = f"providers.{provider_key}_oauth"
            class_name = f"{provider_key.title()}OAuth"

            try:
                module = __import__(module_name, fromlist=[class_name])
                provider_class = getattr(module, class_name)

                provider = provider_class()
                token_data = provider.get_token_data()

                if token_data:
                    logger.info("Seeded %s tokens", provider_key)
                else:
                    logger.warning("No tokens found for %s", provider_key)

            except (ImportError, AttributeError):
                logger.warning("Provider %s not available", provider_key)

        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            logger.error("Failed to seed %s: %s", provider_key, e)


if __name__ == "__main__":
    print("OAuth Base Library")
    print("==================")
    print(f"Vault: {VAULT}")
    print(f"tmpfs: {TMPFS_DIR}")
    print(f"Providers: {list(PROVIDER_CONFIG.keys())}")
    print()
    print("To seed tmpfs cache:")
    print("  seed_tmpfs_from_1password()")