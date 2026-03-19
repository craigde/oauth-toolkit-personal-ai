#!/usr/bin/env python3
"""
API Key Manager — Two-Tier Key Management

Same architecture as OAuth tokens:
  Tier 1: tmpfs (/dev/shm) — RAM-backed, ~3ms reads
  Tier 2: 1Password vault — durable, ~1200ms reads

For static API keys that don't need refresh — just fast, secure retrieval.

Usage:
    from key_manager import KeyManager
    
    # Configure with your API keys
    config = {
        "openai": {
            "item_name": "OpenAI API Key",
            "field": "credential", 
            "cache_file": "api-key-openai",
            "env_var": "OPENAI_API_KEY",
        },
    }
    
    km = KeyManager(api_keys=config, vault="Personal")
    key = km.get_key("openai")
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Dict

# Default configuration - customize these for your setup
DEFAULT_VAULT = os.getenv("KEY_MANAGER_VAULT", "Personal")
DEFAULT_TMPFS_DIR = Path("/dev/shm")

# Example API key configuration — replace with your own
DEFAULT_API_KEYS: Dict[str, Dict[str, str]] = {
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
    "brave": {
        "item_name": "Brave Search API Key",
        "field": "credential",
        "cache_file": "api-key-brave",
        "env_var": "BRAVE_API_KEY",
    },
}


class KeyManager:
    """
    API Key Manager with two-tier caching.
    
    Provides fast access to API keys with 1Password backup storage.
    Keys are cached in tmpfs (RAM) for sub-millisecond access.
    """
    
    def __init__(self,
                 api_keys: Optional[Dict[str, Dict[str, str]]] = None,
                 vault: str = DEFAULT_VAULT,
                 tmpfs_dir: Path = DEFAULT_TMPFS_DIR):
        """
        Initialize KeyManager.
        
        Args:
            api_keys: Dictionary mapping key names to configuration dicts.
                     Each config should have: item_name, field, cache_file, env_var
            vault: 1Password vault name
            tmpfs_dir: tmpfs directory for caching (usually /dev/shm)
        """
        self.api_keys = api_keys or DEFAULT_API_KEYS
        self.vault = vault
        self.tmpfs_dir = tmpfs_dir

    def get_key(self, name: str) -> Optional[str]:
        """
        Get an API key by name. Resolution order:
          1. tmpfs cache (~3ms)
          2. 1Password vault (~1200ms), then cache to tmpfs
        """
        if name not in self.api_keys:
            raise ValueError(f"Unknown key '{name}'. Valid: {list(self.api_keys.keys())}")

        config = self.api_keys[name]
        cache_path = self.tmpfs_dir / config["cache_file"]

        # Tier 1: tmpfs cache
        if cache_path.exists():
            try:
                key = cache_path.read_text().strip()
                if key:
                    return key
            except OSError:
                pass

        # Tier 2: 1Password
        key = self._read_from_1password(config["item_name"], config["field"])
        if key:
            self._write_to_cache(cache_path, key)
            print(f"✅ [{name}] Loaded from 1Password, cached to tmpfs")
            return key

        print(f"❌ [{name}] Key not found in 1Password")
        return None

    def seed_all(self):
        """Pre-load all API keys from 1Password into tmpfs cache."""
        print("🔐 Seeding API keys from 1Password → tmpfs...")
        for name in self.api_keys:
            self.get_key(name)

        print("\n📦 Cached keys:")
        for name in self.api_keys:
            cache_path = self.tmpfs_dir / self.api_keys[name]["cache_file"]
            status = "✅" if cache_path.exists() else "❌"
            print(f"  {status} {name}: {cache_path}")

    def seed_to_env(self):
        """Seed all API keys into the current process environment."""
        print("🔐 Seeding API keys to environment...")
        for name, config in self.api_keys.items():
            key = self.get_key(name)
            if key:
                os.environ[config["env_var"]] = key
                print(f"✅ [{name}] Set ${config['env_var']}")
            else:
                print(f"⚠️  [{name}] Not available")

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
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value if value else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"❌ 1Password read failed for {item_name}: {e}")
            return None

    def _write_to_cache(self, cache_path: Path, value: str) -> bool:
        """
        Write a value to tmpfs cache with restricted permissions.

        Uses atomic write: create temp file with 600 perms via os.open(),
        then rename. Avoids TOCTOU race where file is briefly world-readable.
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


# Convenience: default instance and module-level functions
_default = KeyManager()

def get_key(name: str) -> Optional[str]:
    return _default.get_key(name)

def seed_all():
    _default.seed_all()

def seed_to_env():
    _default.seed_to_env()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        seed_all()
    elif len(sys.argv) > 1 and sys.argv[1] == "env":
        seed_to_env()
    elif len(sys.argv) > 1:
        key = get_key(sys.argv[1])
        if key:
            print(f"{key[:20]}...")
        else:
            sys.exit(1)
    else:
        print("Usage:")
        print("  key_manager.py seed        — Pre-load all keys to tmpfs")
        print("  key_manager.py env         — Seed keys to environment")
        print("  key_manager.py <name>      — Get a specific key")
        print(f"  Available keys: {list(DEFAULT_API_KEYS.keys())}")
        print()
        print("For custom config, import KeyManager class:")
        print("  from key_manager import KeyManager")
        print("  km = KeyManager(api_keys=my_config, vault='MyVault')")
