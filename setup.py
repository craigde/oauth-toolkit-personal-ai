#!/usr/bin/env python3
"""
OAuth Toolkit for Personal AI - Setup Script
Initializes the repository and validates the installation.
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def check_dependencies():
    """Check for required dependencies."""
    print("🔍 Checking dependencies...")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        return False
    
    print(f"✅ Python {sys.version.split()[0]}")
    
    # Check for required packages
    try:
        import requests
        print("✅ requests package available")
    except ImportError:
        print("❌ requests package not found")
        print("   Install with: pip install requests")
        return False
    
    # Check for 1Password CLI
    try:
        result = subprocess.run(["op", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 1Password CLI {result.stdout.strip()}")
        else:
            print("❌ 1Password CLI not working")
            return False
    except FileNotFoundError:
        print("❌ 1Password CLI not found")
        print("   Install from: https://developer.1password.com/docs/cli/")
        return False
    
    return True


def validate_project_structure():
    """Validate that all required files are present."""
    print("\n📁 Validating project structure...")
    
    required_files = [
        "oauth_base.py",
        "providers/google_oauth.py",
        "providers/template_oauth.py",
        "examples/basic_usage.py",
        "examples/voice_call_demo.py",
        "examples/systemd_setup.sh",
        "tests/test_oauth_base.py",
        "README.md",
        "LICENSE"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✅ All required files present")
    return True


def setup_git_repository():
    """Initialize git repository if not already done."""
    print("\n📦 Setting up git repository...")
    
    if Path(".git").exists():
        print("✅ Git repository already initialized")
        return True
    
    try:
        subprocess.run(["git", "init"], check=True, capture_output=True)
        print("✅ Git repository initialized")
        
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        print("✅ Files staged")
        
        subprocess.run([
            "git", "commit", "-m", 
            "Initial commit: OAuth Toolkit for Personal AI\n\n"
            "Features:\n"
            "- Two-tier token storage (tmpfs + 1Password)\n"
            "- Sub-millisecond token access for voice applications\n"
            "- Google OAuth provider with auto-refresh\n"
            "- Template for custom providers\n"
            "- Systemd integration for boot-time cache seeding\n"
            "- Comprehensive examples and documentation"
        ], check=True, capture_output=True)
        print("✅ Initial commit created")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git setup failed: {e}")
        return False
    except FileNotFoundError:
        print("⚠️  Git not found - repository not initialized")
        return True  # Not a failure, just not available


def create_example_config():
    """Create example configuration files."""
    print("\n⚙️  Creating example configuration...")
    
    # Create providers/__init__.py
    providers_init = Path("providers/__init__.py")
    if not providers_init.exists():
        providers_init.write_text('"""OAuth providers for personal AI applications."""\n')
        print("✅ Created providers/__init__.py")
    
    # Create examples/__init__.py
    examples_init = Path("examples/__init__.py")
    if not examples_init.exists():
        examples_init.write_text('"""Usage examples for OAuth toolkit."""\n')
        print("✅ Created examples/__init__.py")
    
    # Create configuration template
    config_template = Path("config.example.py")
    if not config_template.exists():
        config_template.write_text("""#!/usr/bin/env python3
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
""")
        print("✅ Created config.example.py")


def run_basic_tests():
    """Run basic validation tests."""
    print("\n🧪 Running basic tests...")
    
    try:
        # Test imports
        sys.path.insert(0, str(Path.cwd()))
        
        from oauth_base import OAuthBase, PROVIDER_CONFIG
        print("✅ oauth_base imports successfully")
        
        from providers.google_oauth import GoogleOAuth
        print("✅ google_oauth imports successfully")
        
        # Test provider configuration
        if "google" in PROVIDER_CONFIG:
            print("✅ Google provider configured")
        else:
            print("⚠️  Google provider not in PROVIDER_CONFIG")
        
        # Run unit tests if available
        try:
            result = subprocess.run([
                sys.executable, "-m", "pytest", "tests/", "-v"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ Unit tests passed")
            else:
                print("⚠️  Some unit tests failed:")
                print(result.stdout[-500:])  # Last 500 chars
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback to direct test execution
            result = subprocess.run([
                sys.executable, "tests/test_oauth_base.py"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ Basic tests passed")
            else:
                print("⚠️  Basic tests had issues:")
                print(result.stderr[-300:])  # Last 300 chars
        
        return True
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return False


def show_next_steps():
    """Show next steps for setup."""
    print("\n🚀 Setup completed! Next steps:")
    print()
    print("1. 📋 Configure OAuth credentials:")
    print("   • Copy config.example.py to config.py")
    print("   • Add your OAuth client IDs and secrets")
    print("   • Update provider configurations")
    print()
    print("2. 🔐 Set up 1Password items:")
    print("   • Create OAuth token items in your vault")
    print("   • Use the exact item names from PROVIDER_CONFIG")
    print("   • Store tokens in oauth_data field as JSON")
    print()
    print("3. 🧪 Test the setup:")
    print("   • python3 examples/basic_usage.py")
    print("   • python3 examples/voice_call_demo.py")
    print()
    print("4. 🔧 Optional: Set up systemd service:")
    print("   • chmod +x examples/systemd_setup.sh")
    print("   • ./examples/systemd_setup.sh")
    print()
    print("5. 📚 Read the documentation:")
    print("   • README.md for detailed setup instructions")
    print("   • providers/template_oauth.py for custom providers")
    print()
    print("🎉 Happy coding with secure, fast OAuth!")


def main():
    """Main setup function."""
    print("OAuth Toolkit for Personal AI - Setup")
    print("=" * 50)
    
    success = True
    
    success &= check_dependencies()
    success &= validate_project_structure()
    
    if success:
        setup_git_repository()  # Optional, don't fail if git unavailable
        create_example_config()
        success &= run_basic_tests()
    
    if success:
        show_next_steps()
        print("\n✅ Setup completed successfully!")
        return 0
    else:
        print("\n❌ Setup failed - please address the issues above")
        return 1


if __name__ == "__main__":
    sys.exit(main())