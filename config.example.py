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
# Store OAuth app credentials in 1Password using the two-tier system:
#
# 1. Create 1Password item: "Google OAuth App"
# 2. Add field "app_credentials" with JSON content:
#    {
#      "client_id": "your-client-id.apps.googleusercontent.com",
#      "client_secret": "your-client-secret"  
#    }
#
# The system will cache credentials in tmpfs for fast access
# while keeping them securely encrypted in 1Password vault.

# Provider endpoint overrides (rarely needed)
# GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # Default
# GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"  # Default
