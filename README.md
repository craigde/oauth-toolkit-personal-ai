# Personal AI Secrets Toolkit

A production-ready, two-tier secrets management system for personal AI applications. Covers OAuth tokens, API keys, and encrypted boot unlock — everything your AI assistant needs to handle credentials securely and fast.

Built for [Pearl](https://medium.com/@craigdewar), an AI assistant running on a Raspberry Pi aboard a houseboat in Seattle.

**Blog series:**
- [Part 1: Building a Bulletproof Auth System for Personal AI](https://medium.com/@craigdewar) — OAuth token management
- [Part 2: The Master Key Problem](https://medium.com/@craigdewar) — Encrypted boot unlock

## The Problem

Personal AI assistants need secure, fast access to multiple APIs. Traditional solutions force a choice:

- **Security**: Encrypted storage that's too slow for voice calls (1200ms latency)
- **Performance**: Fast access with plaintext tokens on disk (security nightmare)

We solved both. And then we noticed the master key was still in plaintext.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  On Disk                          │
│  encrypted_token.enc    AES-256 encrypted blob    │
│  config.json            Bot token (low value)     │
│  Nothing else sensitive.                          │
└──────────────────────────────────────────────────┘
                        │
                   Boot + Passphrase
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│               In RAM (tmpfs /dev/shm)             │
│  decrypted-token          Master vault key        │
│  api-key-*                API keys                │
│  oauth-token-*.json       OAuth tokens            │
│  All 600 permissions. Vanishes on power-off.      │
└──────────────────────────────────────────────────┘
                        │
                   Auto-fallback
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│            1Password Vault (Encrypted)            │
│  OAuth refresh tokens, API keys, credentials      │
│  ~1200ms access, used as fallback + refresh       │
└──────────────────────────────────────────────────┘
```

## Three Components

### 1. OAuth Token Manager (`oauth_base.py` + `providers/`)

Two-tier OAuth with auto-refresh. Tokens live in RAM for speed, backed by 1Password for durability.

```python
from providers.google_oauth import GoogleOAuth

google = GoogleOAuth()
token = google.get_access_token()  # 3ms from tmpfs, 1200ms fallback to 1Password
```

- **Hot path**: ~3ms (tmpfs RAM cache)
- **Cold path**: ~1200ms (1Password, then backfills tmpfs)
- **Auto-refresh**: Expired tokens refresh transparently, persist to both tiers
- **Provider-specific**: Google (ISO 8601 expiry), Microsoft (Unix timestamp + offset), Spotify, custom template

### 2. API Key Manager (`key_manager.py`)

Same two-tier pattern for static API keys. No refresh logic needed — just fast, secure retrieval.

```python
from key_manager import KeyManager

config = {
    "openai": {
        "item_name": "OpenAI API Key",
        "field": "credential",
        "cache_file": "api-key-openai",
        "env_var": "OPENAI_API_KEY",
    },
}

km = KeyManager(api_keys=config, vault="Personal")
key = km.get_key("openai")      # 3ms from tmpfs
km.seed_all()                    # Pre-load all keys at startup
km.seed_to_env()                 # Export to environment variables
```

### 3. Boot Unlock (`boot_unlock.py`)

The master key problem: every secret depends on the 1Password service account token. We encrypt it on disk and require a human passphrase at boot via Telegram.

```
Pi boots → asks for passphrase via Telegram → decrypts vault key → seeds to RAM → starts services
```

**Security properties:**
- Master token never in plaintext on disk (AES-256-CBC, PBKDF2, 600K iterations)
- Passphrase delivered via Telegram, message deleted before AI connects
- Passphrase passed to openssl via `fd:N`, never in `/proc/cmdline`
- Brute force protection: 3 attempts then 10-minute cooldown
- AI assistant literally cannot start without human authorization

```bash
# Initial setup — encrypt your 1Password service account token
python3 boot_unlock.py encrypt

# On boot (runs as systemd service)
python3 boot_unlock.py boot

# Change passphrase
python3 boot_unlock.py rekey
```

## Quick Start

### Prerequisites
```bash
pip install requests
# Install 1Password CLI: https://developer.1password.com/docs/cli/
```

### OAuth Setup
```bash
# Store OAuth credentials in 1Password
op item create --category="Login" --title="Google OAuth Token" \
  --vault="Personal" \
  --field="token_json={\"access_token\":\"...\",\"refresh_token\":\"...\",\"client_id\":\"...\",\"client_secret\":\"...\",\"expiry\":\"2025-03-10T18:30:00+00:00\",\"token_uri\":\"https://oauth2.googleapis.com/token\"}"
```

### API Key Setup
```bash
# Store API keys in 1Password
op item create --category="API Credential" --title="OpenAI API Key" \
  --vault="Personal" \
  "credential=sk-your-key-here"
```

### Boot Unlock Setup
```bash
# 1. Encrypt the master token
python3 boot_unlock.py encrypt
# 2. Edit CONFIG section in boot_unlock.py with your Telegram chat ID
# 3. Install systemd services (see examples/systemd_setup.sh)
# 4. Remove plaintext token from .env
```

## Systemd Integration

The boot chain ensures secrets are available before your AI starts:

```
boot_unlock.service (oneshot, waits for passphrase)
    → your-gateway.service (depends on boot_unlock)
        → reads secrets from tmpfs, seeds API keys
        → AI assistant is alive
```

Drop-in overrides survive third-party service file updates:

```ini
# ~/.config/systemd/user/your-gateway.service.d/secrets.conf
[Unit]
After=boot_unlock.service
Requires=boot_unlock.service

[Service]
ExecStart=
ExecStart=/path/to/your/gateway-wrapper.sh
```

See `examples/systemd_setup.sh` for the complete setup.

## Adding a Custom OAuth Provider

```python
from oauth_base import OAuthBase

class CustomOAuth(OAuthBase):
    PROVIDER = "custom"  # Must match key in PROVIDER_CONFIG
    
    def refresh_token(self, force=False):
        # Your refresh logic here
        token_data = self.get_token_data()
        # ... call provider's token endpoint ...
        self.save_token(new_token_data)  # Saves to both tiers
        return True
```

Add your provider to `PROVIDER_CONFIG` in `oauth_base.py`:
```python
PROVIDER_CONFIG = {
    "custom": {
        "item_name": "Custom OAuth Token",  # 1Password item name
        "cache_file": "oauth-token-custom.json",  # tmpfs filename
    },
}
```

## Security Details

### TOCTOU-Safe File Writes
All tmpfs writes use `os.open()` with 0o600 permissions and atomic rename. Files are never visible with wrong permissions:

```python
fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, data)
os.close(fd)
tmp_path.rename(final_path)  # Atomic
```

### Passphrase Never in Process List
Boot unlock passes passphrases to openssl via file descriptor, not command line:
```python
pass_read, pass_write = os.pipe()
os.write(pass_write, passphrase.encode())
os.close(pass_write)
subprocess.run(["openssl", ..., "-pass", f"fd:{pass_read}"], pass_fds=(pass_read,))
```

### Secret Hierarchy
```
Telegram bot token (on disk)         → Low value: can impersonate bot
Encrypted master token (on disk)     → Useless without passphrase
1Password vault (cloud)              → All secrets, accessed via master token
tmpfs cache (RAM)                    → Fast access, vanishes on power-off
```

## Real-World Performance

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| OAuth token access | 1200ms | 3ms | 400x |
| API key retrieval | 1200ms | 3ms | 400x |
| Boot to ready | Manual | 17s* | Automated |

\*From passphrase entry to AI assistant online.

## Project Structure

```
├── oauth_base.py           # Core two-tier token management
├── key_manager.py          # API key management (same pattern)
├── boot_unlock.py          # Encrypted boot unlock via Telegram
├── providers/
│   ├── google_oauth.py     # Google Calendar/Gmail
│   ├── template_oauth.py   # Template for new providers
│   └── __init__.py
├── examples/
│   ├── basic_usage.py      # Quick start examples
│   ├── systemd_setup.sh    # Service file installation
│   └── voice_call_demo.py  # Voice call integration
└── tests/
```

## License

MIT License — see [LICENSE](LICENSE)

## Acknowledgments

Battle-tested on Pearl, an AI assistant running on a Raspberry Pi aboard a houseboat on Lake Union, Seattle. Three months of daily production use, dozens of OAuth-protected operations per day, zero authentication failures.
