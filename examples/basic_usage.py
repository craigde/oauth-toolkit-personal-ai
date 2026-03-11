#!/usr/bin/env python3
"""
Basic OAuth Usage Examples
Demonstrates core functionality of the two-tier OAuth system.
"""

import requests
from pathlib import Path
import sys

# Add providers to path
sys.path.append(str(Path(__file__).parent.parent))

from providers.google_oauth import GoogleOAuth


def example_google_calendar():
    """Example: Access Google Calendar API with automatic token management."""
    print("🗓️  Google Calendar Example")
    print("=" * 40)
    
    # Get OAuth token (auto-fallback: tmpfs → 1Password → refresh)
    google = GoogleOAuth()
    token = google.get_access_token()
    
    if not token:
        print("❌ No Google token available. Run initial setup first.")
        return
    
    print("✅ Got OAuth token (source: tmpfs cache or 1Password)")
    
    # Use token in API call
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        # List calendars
        response = requests.get(
            'https://www.googleapis.com/calendar/v3/users/me/calendarList',
            headers=headers
        )
        
        if response.status_code == 200:
            calendars = response.json()
            print(f"📅 Found {len(calendars.get('items', []))} calendars:")
            for cal in calendars.get('items', [])[:3]:  # Show first 3
                print(f"   - {cal.get('summary', 'Unknown')}")
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.RequestException as e:
        print(f"❌ Network error: {e}")


def example_token_refresh():
    """Example: Force token refresh and verify it works."""
    print("\n🔄 Token Refresh Example")
    print("=" * 40)
    
    google = GoogleOAuth()
    
    # Get current token info
    current_token = google.get_access_token()
    if not current_token:
        print("❌ No token available for refresh test")
        return
    
    print(f"🔍 Current token: {current_token[:20]}...")
    
    # Force refresh
    print("🔄 Forcing token refresh...")
    if google.refresh_token(force=True):
        new_token = google.get_access_token()
        print(f"✅ New token: {new_token[:20]}...")
        
        # Verify tokens are different (usually)
        if new_token != current_token:
            print("✅ Token was updated")
        else:
            print("ℹ️  Token unchanged (some providers reuse tokens)")
    else:
        print("❌ Token refresh failed")


def example_performance_timing():
    """Example: Measure token access performance."""
    print("\n⚡ Performance Timing Example")
    print("=" * 40)
    
    import time
    
    google = GoogleOAuth()
    
    # Time multiple token access calls
    times = []
    for i in range(5):
        start = time.time()
        token = google.get_access_token()
        end = time.time()
        
        if token:
            access_time = (end - start) * 1000  # Convert to milliseconds
            times.append(access_time)
            print(f"Access {i+1}: {access_time:.1f}ms")
        else:
            print(f"Access {i+1}: Failed")
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\n📊 Performance Summary:")
        print(f"   Average: {avg_time:.1f}ms")
        print(f"   Range: {min_time:.1f}ms - {max_time:.1f}ms")
        
        if avg_time < 10:
            print("✅ Excellent - hitting tmpfs cache")
        elif avg_time < 100:
            print("⚠️  Good - may be hitting 1Password occasionally")
        else:
            print("❌ Slow - check 1Password CLI performance")


def example_error_handling():
    """Example: Demonstrate error handling and fallback behavior."""
    print("\n🛡️  Error Handling Example")
    print("=" * 40)
    
    google = GoogleOAuth()
    
    # Test with invalid token
    print("🔍 Testing token validation...")
    if google.test_token("invalid_token"):
        print("❌ Validation failed - invalid token accepted")
    else:
        print("✅ Validation working - invalid token rejected")
    
    # Test with valid token
    valid_token = google.get_access_token()
    if valid_token:
        if google.test_token(valid_token):
            print("✅ Valid token accepted")
        else:
            print("⚠️  Valid token rejected - may be expired")
    
    # Test auto-refresh on expired token
    print("\n🔄 Testing auto-refresh behavior...")
    token_data = google.get_token_data()
    if token_data:
        # Check if provider has freshness validation
        validation_fn = google._get_validation_function()
        if validation_fn:
            is_fresh = validation_fn(token_data)
            print(f"Token freshness: {'✅ Fresh' if is_fresh else '⚠️ Stale'}")
        else:
            print("ℹ️  No freshness validation for this provider")


def example_multi_provider():
    """Example: Using multiple OAuth providers simultaneously."""
    print("\n🔀 Multi-Provider Example")
    print("=" * 40)
    
    providers = []
    
    # Try to load all available providers
    try:
        from providers.google_oauth import GoogleOAuth
        providers.append(("Google", GoogleOAuth()))
    except ImportError:
        print("⚠️  Google provider not available")
    
    # Add more providers as they become available
    # try:
    #     from providers.microsoft_oauth import MicrosoftOAuth
    #     providers.append(("Microsoft", MicrosoftOAuth()))
    # except ImportError:
    #     pass
    
    print(f"🔍 Testing {len(providers)} provider(s)...")
    
    for name, provider in providers:
        token = provider.get_access_token()
        if token:
            print(f"✅ {name}: Token available ({len(token)} chars)")
            
            # Test the token
            if provider.test_token(token):
                print(f"   ✅ {name}: Token valid")
            else:
                print(f"   ⚠️ {name}: Token invalid or expired")
        else:
            print(f"❌ {name}: No token available")


if __name__ == "__main__":
    print("OAuth Toolkit - Basic Usage Examples")
    print("=" * 50)
    
    try:
        example_google_calendar()
        example_token_refresh()
        example_performance_timing()
        example_error_handling()
        example_multi_provider()
        
        print(f"\n🎉 All examples completed!")
        print(f"\nNext steps:")
        print(f"   - Check your Google Calendar API access")
        print(f"   - Monitor tmpfs vs 1Password access patterns")
        print(f"   - Add more providers as needed")
        
    except Exception as e:
        print(f"\n❌ Example failed with error: {e}")
        print(f"Make sure you have:")
        print(f"   - 1Password CLI installed and authenticated")
        print(f"   - OAuth tokens stored in 1Password vault")
        print(f"   - Correct provider configuration")