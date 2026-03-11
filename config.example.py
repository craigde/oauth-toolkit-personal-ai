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

# OAuth Configuration
# Store ALL OAuth data together in one 1Password item per provider:
#
# 1. Create 1Password item: "Google OAuth Token"  
# 2. Add field "token_json" with complete OAuth data:
#    {
#      "access_token": "your_access_token",
#      "refresh_token": "your_refresh_token",
#      "client_id": "your-client-id.apps.googleusercontent.com", 
#      "client_secret": "your-client-secret",
#      "expiry": "2025-03-10T18:30:00+00:00",
#      "token_uri": "https://oauth2.googleapis.com/token"
#    }
#
# This approach (Pearl's method) stores everything together:
# - Simpler: One secret per provider (not separate token/app items)
# - Faster: One tmpfs cache file (not separate caches)  
# - More secure: Atomic updates of all OAuth data together

# Provider endpoint overrides (rarely needed)
# GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # Default
# GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"  # Default
