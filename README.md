# Personal AI OAuth Toolkit

A production-ready, two-tier OAuth token management system designed for personal AI applications that require both security and performance.

## The Problem

Personal AI assistants need secure, fast access to multiple OAuth-protected APIs (Google Calendar, Microsoft To Do, Spotify, etc.). Traditional solutions force you to choose between:

- **Security**: Encrypted storage that's too slow for voice calls (1200ms latency)
- **Performance**: Fast access with plaintext tokens (security nightmare)

## Our Solution: Two-Tier Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│ AI Processes    │    │ tmpfs Cache  │    │ 1Password Vault │
│ (voice, chat,   │ ←→ │ (RAM-only,   │ ←→ │ (encrypted,     │
│  cron jobs)     │    │  ~3ms access)│    │  ~1200ms access)│
└─────────────────┘    └──────────────┘    └─────────────────┘
```

### Performance
- **Hot path**: ~3ms token access via tmpfs (RAM-based cache)
- **Cold path**: ~1200ms via 1Password (encrypted backup)
- **Auto-fallback**: Seamless degradation when cache misses

### Security
- **RAM-only cache**: tmpfs vanishes on reboot
- **Encrypted backup**: 1Password vault for durability
- **Per-provider isolation**: Separate files prevent cross-contamination
- **Auto-refresh**: Handles token expiration transparently

## Quick Start

### 1. Install Dependencies
```bash
pip install requests
# Install 1Password CLI: https://developer.1password.com/docs/cli/
```

### 2. Setup 1Password
```bash
# Create OAuth token items in 1Password
op item create --category="Login" --title="Google OAuth Token" \
  --field="oauth_data={\"access_token\":\"your_token\",\"refresh_token\":\"your_refresh\",\"expiry\":\"2025-03-10T18:30:00+00:00\"}"

# Create OAuth app credentials (client_id, client_secret)  
op item create --category="Login" --title="Google OAuth App" \
  --field="app_credentials={\"client_id\":\"your-client-id.apps.googleusercontent.com\",\"client_secret\":\"your-client-secret\"}"
```

### 3. Basic Usage
```python
from providers.google_oauth import GoogleOAuth

# Get a token (fast path: tmpfs, fallback: 1Password)
google = GoogleOAuth()
token = google.get_access_token()

# Use in API calls
headers = {'Authorization': f'Bearer {token}'}
response = requests.get('https://www.googleapis.com/calendar/v3/calendars/primary/events', 
                       headers=headers)
```

## Architecture

### Core Components

- **`oauth_base.py`**: Shared infrastructure for all providers
- **`providers/*.py`**: Provider-specific implementations
- **`examples/`**: Usage patterns and integration examples

### Provider Support

| Provider | Status | Scopes |
|----------|--------|--------|
| Google | ✅ Complete | Calendar, Gmail |
| Microsoft | ✅ Complete | To Do API |
| Spotify | ✅ Complete | Web API |
| Custom | 📝 Template | Any OAuth2 |

### Storage Tiers

#### Tier 1: tmpfs Cache
- **Location**: `/dev/shm/oauth-token-{provider}.json`
- **Access time**: ~3ms
- **Security**: RAM-only, owner-read (600), vanishes on reboot
- **Isolation**: Per-provider files

#### Tier 2: 1Password Vault
- **Location**: Encrypted 1Password vault
- **Access time**: ~1200ms
- **Security**: End-to-end encrypted
- **Durability**: Survives reboots, hardware failures

## Advanced Features

### Auto-refresh
```python
# Tokens refresh automatically when expired
google = GoogleOAuth()
token = google.get_access_token()  # Always valid

# Force refresh
google.refresh_token(force=True)
```

### Process Environment Updates
```python
# For voice calls and child processes
google.get_access_token()  # Updates os.environ automatically
```

### Boot-time Cache Warming
```bash
# Systemd service to warm cache on startup
python3 -c "from oauth_base import seed_tmpfs_from_1password; seed_tmpfs_from_1password()"
```

## Real-World Performance

**Before**: Voice assistant OAuth calls took 1200ms  
**After**: Voice assistant OAuth calls take 3ms (400x improvement)

**Use case**: "Add baseball games to calendar" during voice call
- User speaks command
- AI needs Google Calendar access
- Token retrieved in 3ms (tmpfs hit)
- Calendar updated instantly
- Response feels natural

## Security Model

### Defense in Depth
1. **File permissions**: 600 (owner-only)
2. **RAM storage**: tmpfs (no disk persistence)
3. **Encrypted backup**: 1Password vault
4. **Process isolation**: Per-provider token files

### Threat Protection
- ✅ **Token theft**: Encrypted 1Password backup
- ✅ **Memory dumps**: tmpfs protection
- ✅ **Process inspection**: Environment variables updated safely
- ✅ **Reboot persistence**: Auto-restore from 1Password

## Provider Examples

### Adding Google Support
```python
from providers.google_oauth import GoogleOAuth

google = GoogleOAuth()
token = google.get_access_token()

# Use with Google APIs
calendar_response = requests.get(
    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
    headers={'Authorization': f'Bearer {token}'}
)
```

### Adding Custom Provider
```python
from oauth_base import OAuthBase

class CustomOAuth(OAuthBase):
    PROVIDER = "custom"
    
    def refresh_token(self, force: bool = False) -> bool:
        # Implement your OAuth refresh logic
        pass
```

## Production Deployment

### Systemd Integration
```ini
# /etc/systemd/system/oauth-seeder.service
[Unit]
Description=OAuth Token Cache Seeder
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -c "from oauth_base import seed_tmpfs_from_1password; seed_tmpfs_from_1password()"
User=your-user

[Install]
WantedBy=multi-user.target
```

### Voice Application Integration
```python
# For sub-millisecond token access in voice calls
google = GoogleOAuth()
token = google.get_access_token()  # 3ms typical

# Use immediately in voice response
calendar_data = get_calendar_events(token)
speak(f"You have {len(calendar_data)} events today")
```

## Contributing

1. **Fork the repository**
2. **Create provider file** using `providers/template_oauth.py`
3. **Add tests** in `tests/`
4. **Update documentation**
5. **Submit pull request**

## License

MIT License - see [LICENSE](LICENSE)

## Acknowledgments

Built for [Pearl](https://medium.com/@craigdewar/building-a-bulletproof-oauth-system-for-personal-ai), an AI assistant running on a houseboat in Seattle. Tested in production handling voice calls, calendar management, smart home control, and music automation.

---

**Need help?** Open an issue or check the [examples/](examples/) directory for usage patterns.