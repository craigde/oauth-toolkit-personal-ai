#!/usr/bin/env python3
'''
OAuth Toolkit Configuration Example
Copy this to config.py and customize for your setup.
'''

# 1Password Configuration
VAULT_NAME = "Personal"  # Your 1Password vault name

# Provider-specific OAuth credentials
GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your-client-secret"

# Add other provider credentials here
# MICROSOFT_CLIENT_ID = "your-microsoft-client-id"
# SPOTIFY_CLIENT_ID = "your-spotify-client-id"

# Performance tuning
TMPFS_DIR = "/dev/shm"  # RAM-based cache directory
TOKEN_REFRESH_BUFFER_SECONDS = 300  # 5-minute buffer for token refresh
