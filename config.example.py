#!/usr/bin/env python3
'''
OAuth Toolkit Configuration Example
Copy this to config.py and customize for your setup.

SECURITY NOTE: Never put OAuth credentials in config files!
All secrets should be stored in 1Password vault and accessed via environment variables.
'''

# 1Password Configuration
VAULT_NAME = "Personal"  # Your 1Password vault name

# Performance tuning
TMPFS_DIR = "/dev/shm"  # RAM-based cache directory
TOKEN_REFRESH_BUFFER_SECONDS = 300  # 5-minute buffer for token refresh

# OAuth Client Configuration
# Store actual credentials as environment variables or in 1Password:
#   export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
#   export GOOGLE_CLIENT_SECRET="your-client-secret"
# 
# Or better yet, store in 1Password and load via:
#   op item get "Google OAuth App" --vault Personal --fields client_id --reveal

# Provider endpoint overrides (rarely needed)
# GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # Default
# GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"  # Default
