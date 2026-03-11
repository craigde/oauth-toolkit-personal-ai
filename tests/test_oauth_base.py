#!/usr/bin/env python3
"""
Basic tests for OAuth Base functionality
"""

import unittest
import tempfile
import json
import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from oauth_base import OAuthBase


class MockOAuth(OAuthBase):
    """Mock OAuth provider for testing."""
    PROVIDER = "test"
    
    def refresh_token(self, force: bool = False) -> bool:
        """Mock refresh implementation."""
        return True


class TestOAuthBase(unittest.TestCase):
    """Test OAuth base functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Update PROVIDER_CONFIG for testing
        from oauth_base import PROVIDER_CONFIG
        PROVIDER_CONFIG["test"] = {"item_name": "Test OAuth Token"}
        
        # Create temporary directory for tmpfs simulation
        self.temp_dir = tempfile.mkdtemp()
        
        # Monkey patch tmpfs directory
        self.original_tmpfs_dir = OAuthBase._tmpfs_path
        OAuthBase._tmpfs_path = lambda self: Path(self.temp_dir) / f"oauth-token-{self.PROVIDER}.json"
        
        self.oauth = MockOAuth()
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original tmpfs path
        OAuthBase._tmpfs_path = self.original_tmpfs_dir
        
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_tmpfs_read_write(self):
        """Test tmpfs cache read/write operations."""
        test_data = {"access_token": "test_token", "expires_in": 3600}
        
        # Write to tmpfs
        self.oauth._write_to_tmpfs(test_data)
        
        # Read from tmpfs
        read_data = self.oauth._read_from_tmpfs()
        
        self.assertEqual(read_data, test_data)
    
    def test_tmpfs_file_permissions(self):
        """Test that tmpfs files have correct permissions."""
        test_data = {"access_token": "test_token"}
        
        self.oauth._write_to_tmpfs(test_data)
        
        tmpfs_path = self.oauth._tmpfs_path()
        stat_result = os.stat(tmpfs_path)
        permissions = oct(stat_result.st_mode)[-3:]
        
        # Should be 600 (owner read/write only)
        self.assertEqual(permissions, '600')
    
    def test_token_field_normalization(self):
        """Test token field normalization."""
        # Test with legacy 'token' field
        legacy_data = {"token": "legacy_token", "expires_in": 3600}
        normalized = MockOAuth._normalize_token_fields(legacy_data)
        
        self.assertIn("access_token", normalized)
        self.assertEqual(normalized["access_token"], "legacy_token")
        self.assertNotIn("token", normalized)
    
    def test_provider_validation(self):
        """Test provider configuration validation."""
        # Should fail with unknown provider
        with self.assertRaises(ValueError):
            class InvalidOAuth(OAuthBase):
                PROVIDER = "nonexistent"
            InvalidOAuth()
    
    def test_get_access_token_no_data(self):
        """Test get_access_token when no token data available."""
        # Should return None when no data available
        token = self.oauth.get_access_token()
        self.assertIsNone(token)
    
    def test_get_access_token_with_data(self):
        """Test get_access_token with valid data."""
        test_data = {"access_token": "valid_token"}
        
        # Write to tmpfs first
        self.oauth._write_to_tmpfs(test_data)
        
        token = self.oauth.get_access_token()
        self.assertEqual(token, "valid_token")


if __name__ == "__main__":
    unittest.main()