#!/usr/bin/env python3
"""
API Key Manager — 1Password-backed with tmpfs cache

Unlike OAuth tokens (which rotate and need refresh logic), API keys are static.
The problem is the same though: you need them fast and off disk.

Primary flow:
  1Password vault → tmpfs cache (/dev/shm) → your code reads from tmpfs

Optional:
  seed_to_env() exports keys to os.environ for frameworks that expect
  environment variables (Node.js apps, Docker containers, etc.).
  This is a convenience bridge, not the core architecture.

Usage:
    from key_manager import KeyManager

    config = {
        "openai": {
            "item_name": "OpenAI API Key",   # 1Password item name
            "field": "credential",            # 1Password field label
            "cache_file": "api-key-openai",   # tmpfs filename
            "env_var": "OPENAI_API_KEY",      # optional: for seed_to_env()
        },
    }

    km = KeyManager(api_keys=config, vault="Personal")
    key = km.get_key("openai")      # 3ms from tmpfs, 1200ms fallback to 1Password
    km.seed_all()                    # Pre-load all keys at startup
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict

DEFAULT_VAULT = "Personal"
DEFAULT_TMPFS_DIR = Path("/dev/shm")

# Example configuration — replace with your own keys and 1Password item names.
# The env_var field is optional; only used by seed_to_env().
EXAMPLE_API_KEYS: Dict[str, Dict[str, str]] = {
    "openai": {
        "item_name": "OpenAI API Key",
        "field": "credential",
        "cache_file": "api-key-openai",
        "env_var": "OPENAI_API_KEY",
    },
    "elevenlabs": {
        "item_name": "ElevenLabs API Key",
        "field": "credential",
        "cache_file": "api-key-elevenlabs",
        "env_var": "ELEVENLABS_API_KEY",
    },
}


class KeyManager:
    """
    API Key Manager: 1Password → tmpfs cache.

    Keys are read from 1Password on first access (or via seed_all at startup),
    then cached in tmpfs for sub-millisecond subsequent reads. tmpfs is RAM-only
    and vanishes on reboot — nothing sensitive touches the disk.
    """

    def __init__(self,
                 api_keys: Optional[Dict[str, Dict[str, str]]] = None,
                 vault: str = DEFAULT_VAULT,
                 tmpfs_dir: Path = DEFAULT_TMPFS_DIR):
        self.api_keys = api_keys or EXAMPLE_API_KEYS
        self.vault = vault
        self.tmpfs_dir = tmpfs_dir

    def get_key(self, name: str) -> Optional[str]:
        """
        Get an API key by name.

        Resolution order:
          1. tmpfs cache (~3ms)
          2. 1Password vault (~1200ms), then backfill tmpfs
        """
        if name not in self.api_keys:
            raise ValueError(f"Unknown key '{name}'. Valid: {list(self.api_keys.keys())}")

        config = self.api_keys[name]
        cache_path = self.tmpfs_dir / config["cache_file"]

        # Tier 1: tmpfs cache (fast path)
        if cache_path.exists():
            try:
                key = cache_path.read_text().strip()
                if key:
                    return key
            except OSError:
                pass

        # Tier 2: 1Password (slow path, backfills tmpfs)
        key = self._read_from_1password(config["item_name"], config["field"])
        if key:
            self._write_to_cache(cache_path, key)
            print(f"✅ [{name}] Loaded from 1Password, cached to tmpfs")
            return key

        print(f"❌ [{name}] Key not found in 1Password")
        return None

    def seed_all(self):
        """
        Pre-load all API keys from 1Password into tmpfs.

        Call this at service startup so the first real request hits
        the fast path instead of waiting 1200ms for 1Password.
        """
        print("🔐 Seeding API keys: 1Password → tmpfs...")
        for name in self.api_keys:
            self.get_key(name)

        print("\n📦 Cached keys:")
        for name in self.api_keys:
            cache_path = self.tmpfs_dir / self.api_keys[name]["cache_file"]
            status = "✅" if cache_path.exists() else "❌"
            print(f"  {status} {name}: {cache_path}")

    def seed_to_env(self):
        """
        Export all API keys to the current process environment.

        Use this when your framework reads keys from environment variables
        (e.g., Node.js process.env, Docker containers, systemd services).
        This is a convenience bridge — the canonical store is still
        1Password (durable) and tmpfs (fast).
        """
        for name, config in self.api_keys.items():
            env_var = config.get("env_var")
            if not env_var:
                continue
            key = self.get_key(name)
            if key:
                os.environ[env_var] = key
                print(f"✅ [{name}] → ${env_var}")
            else:
                print(f"⚠️  [{name}] Not available, ${env_var} not set")

    # ── Internal ──────────────────────────────────────────────────────

    def _read_from_1password(self, item_name: str, field: str) -> Optional[str]:
        """Read a single field from 1Password."""
        try:
            result = subprocess.run(
                ["op", "item", "get", item_name,
                 "--vault", self.vault,
                 "--fields", f"label={field}",
                 "--reveal"],
                capture_output=True, text=True, check=True, timeout=15,
            )
            value = result.stdout.strip()
            # 1Password CLI sometimes wraps values in quotes
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value if value else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"❌ 1Password read failed for {item_name}: {e}")
            return None

    def _write_to_cache(self, cache_path: Path, value: str) -> bool:
        """
        Write a value to tmpfs with restricted permissions.

        Uses atomic write (os.open with 0o600 + rename) to avoid
        TOCTOU race where the file is briefly world-readable.
        """
        tmp_path = cache_path.with_suffix(".tmp")
        try:
            fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, value.encode())
            finally:
                os.close(fd)
            tmp_path.rename(cache_path)
            return True
        except OSError as e:
            print(f"⚠️  tmpfs cache write failed: {e}")
            tmp_path.unlink(missing_ok=True)
            return False


if __name__ == "__main__":
    import sys

    km = KeyManager()

    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        km.seed_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "env":
        km.seed_all()
        km.seed_to_env()
    elif len(sys.argv) > 1:
        key = km.get_key(sys.argv[1])
        if key:
            print(f"{key[:20]}...")
        else:
            sys.exit(1)
    else:
        print("Usage:")
        print("  key_manager.py seed        — Pre-load all keys to tmpfs")
        print("  key_manager.py env         — Seed to tmpfs + environment variables")
        print("  key_manager.py <name>      — Get a specific key")
        print(f"  Available keys: {list(km.api_keys.keys())}")
