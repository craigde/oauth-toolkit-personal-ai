#!/bin/bash
"""
Systemd Setup for OAuth Cache Seeding
Sets up automatic tmpfs cache warming on system boot.

This ensures that OAuth tokens are available in tmpfs immediately after
system startup, providing fast access from the first API call.
"""

set -euo pipefail

# Configuration
SERVICE_NAME="oauth-cache-seeder"
INSTALL_DIR="/opt/oauth-toolkit"
SERVICE_USER="${USER}"
PYTHON_PATH=$(which python3)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_status "Checking requirements..."
    
    # Check if running as root for systemd operations
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root"
        print_error "Run as your normal user account (it will use sudo when needed)"
        exit 1
    fi
    
    # Check for 1Password CLI
    if ! command -v op &> /dev/null; then
        print_error "1Password CLI not found"
        print_error "Install from: https://developer.1password.com/docs/cli/"
        exit 1
    fi
    
    # Check for Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found"
        exit 1
    fi
    
    # Check if 1Password is authenticated
    if ! op account list &> /dev/null; then
        print_error "1Password CLI not authenticated"
        print_error "Run: op signin"
        exit 1
    fi
    
    print_status "Requirements check passed"
}

create_install_directory() {
    print_status "Creating installation directory..."
    
    sudo mkdir -p "${INSTALL_DIR}"
    sudo chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
    
    # Copy OAuth toolkit files
    cp -r "$(dirname "$0")/../"* "${INSTALL_DIR}/"
    
    print_status "OAuth toolkit installed to ${INSTALL_DIR}"
}

create_seeder_script() {
    print_status "Creating cache seeder script..."
    
    cat > "${INSTALL_DIR}/seed_cache.py" << 'EOF'
#!/usr/bin/env python3
"""
OAuth Cache Seeder
Seeds tmpfs cache with tokens from 1Password on system startup.
"""

import sys
import os
from pathlib import Path

# Add oauth toolkit to path
toolkit_dir = Path(__file__).parent
sys.path.insert(0, str(toolkit_dir))

try:
    from oauth_base import seed_tmpfs_from_1password
    print("🌱 Seeding OAuth token cache...")
    seed_tmpfs_from_1password()
    print("✅ OAuth cache seeding completed")
except Exception as e:
    print(f"❌ OAuth cache seeding failed: {e}")
    sys.exit(1)
EOF

    chmod +x "${INSTALL_DIR}/seed_cache.py"
    print_status "Cache seeder script created"
}

create_systemd_service() {
    print_status "Creating systemd service..."
    
    cat > "/tmp/${SERVICE_NAME}.service" << EOF
[Unit]
Description=OAuth Token Cache Seeder
Documentation=https://github.com/yourusername/oauth-toolkit-personal-ai
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
ExecStart=${PYTHON_PATH} ${INSTALL_DIR}/seed_cache.py
StandardOutput=journal
StandardError=journal
TimeoutStartSec=60
RemainAfterExit=yes

# Environment variables
Environment="PATH=${PATH}"
Environment="HOME=${HOME}"

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/dev/shm
PrivateTmp=yes
ProtectControlGroups=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictRealtime=yes
RestrictNamespaces=yes
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
EOF

    # Install the service file
    sudo mv "/tmp/${SERVICE_NAME}.service" "/etc/systemd/system/"
    sudo chmod 644 "/etc/systemd/system/${SERVICE_NAME}.service"
    
    print_status "Systemd service created"
}

enable_and_start_service() {
    print_status "Enabling and starting service..."
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable service
    sudo systemctl enable "${SERVICE_NAME}.service"
    
    # Start service (test it works)
    sudo systemctl start "${SERVICE_NAME}.service"
    
    # Check status
    if sudo systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        print_status "Service started successfully"
    else
        print_error "Service failed to start"
        sudo systemctl status "${SERVICE_NAME}.service"
        exit 1
    fi
}

create_maintenance_scripts() {
    print_status "Creating maintenance scripts..."
    
    # Status check script
    cat > "${INSTALL_DIR}/check_oauth_status.sh" << 'EOF'
#!/bin/bash
# OAuth System Status Check

echo "OAuth Toolkit Status"
echo "===================="

echo "1. Systemd Service:"
systemctl is-active oauth-cache-seeder.service --quiet && echo "   ✅ Active" || echo "   ❌ Inactive"

echo "2. tmpfs Cache:"
tmpfs_files=$(find /dev/shm -name "oauth-token-*.json" 2>/dev/null | wc -l)
echo "   📁 ${tmpfs_files} provider token files"

echo "3. 1Password CLI:"
if command -v op >/dev/null 2>&1; then
    if op account list >/dev/null 2>&1; then
        echo "   ✅ Authenticated"
    else
        echo "   ❌ Not authenticated"
    fi
else
    echo "   ❌ Not installed"
fi

echo "4. Token Files:"
for token_file in /dev/shm/oauth-token-*.json; do
    if [[ -f "$token_file" ]]; then
        provider=$(basename "$token_file" | sed 's/oauth-token-\(.*\)\.json/\1/')
        age=$(stat -c %Y "$token_file")
        now=$(date +%s)
        age_min=$(( (now - age) / 60 ))
        echo "   📄 ${provider}: ${age_min}min old"
    fi
done

echo ""
echo "Recent service logs:"
journalctl -u oauth-cache-seeder.service --no-pager -l --since "24 hours ago" | tail -5
EOF

    chmod +x "${INSTALL_DIR}/check_oauth_status.sh"
    
    # Manual cache refresh script
    cat > "${INSTALL_DIR}/refresh_oauth_cache.sh" << 'EOF'
#!/bin/bash
# Manually refresh OAuth cache

echo "🔄 Manually refreshing OAuth cache..."
python3 /opt/oauth-toolkit/seed_cache.py

if [[ $? -eq 0 ]]; then
    echo "✅ Cache refresh completed"
else
    echo "❌ Cache refresh failed"
    exit 1
fi
EOF

    chmod +x "${INSTALL_DIR}/refresh_oauth_cache.sh"
    
    print_status "Maintenance scripts created"
}

show_completion_info() {
    print_status "Installation completed successfully!"
    echo ""
    echo "📋 What was installed:"
    echo "   • OAuth toolkit: ${INSTALL_DIR}"
    echo "   • Systemd service: ${SERVICE_NAME}.service"
    echo "   • Cache seeder: ${INSTALL_DIR}/seed_cache.py"
    echo "   • Status checker: ${INSTALL_DIR}/check_oauth_status.sh"
    echo "   • Cache refresher: ${INSTALL_DIR}/refresh_oauth_cache.sh"
    echo ""
    echo "🔧 Useful commands:"
    echo "   • Check service status: systemctl status ${SERVICE_NAME}.service"
    echo "   • View service logs: journalctl -u ${SERVICE_NAME}.service -f"
    echo "   • Check OAuth status: ${INSTALL_DIR}/check_oauth_status.sh"
    echo "   • Refresh cache: ${INSTALL_DIR}/refresh_oauth_cache.sh"
    echo "   • Test manual seeding: sudo systemctl start ${SERVICE_NAME}.service"
    echo ""
    echo "🔄 The service will automatically:"
    echo "   • Start on system boot"
    echo "   • Seed tmpfs with OAuth tokens from 1Password"
    echo "   • Provide fast token access from first API call"
    echo ""
    echo "🧪 Test your setup:"
    echo "   • Reboot and verify fast OAuth token access"
    echo "   • Run the voice_call_demo.py to check performance"
    echo "   • Monitor with ${INSTALL_DIR}/check_oauth_status.sh"
}

# Main execution
main() {
    echo "OAuth Toolkit - Systemd Setup"
    echo "============================="
    echo ""
    
    check_requirements
    create_install_directory
    create_seeder_script
    create_systemd_service
    enable_and_start_service
    create_maintenance_scripts
    show_completion_info
}

# Run if called directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi