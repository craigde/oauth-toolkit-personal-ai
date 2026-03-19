#!/usr/bin/env python3
"""
Boot Unlock — Passphrase-Protected Vault Unlock via Telegram

On boot, asks for a passphrase via Telegram, decrypts the encrypted token,
seeds it to tmpfs, and signals the system is ready.

Security properties:
  - Sensitive tokens never stored in plaintext on disk
  - Passphrase passed to openssl via fd:N (not visible in /proc/pid/cmdline)
  - Telegram passphrase message deleted immediately after reading
  - After decryption, token lives only in tmpfs (RAM)

Usage:
  boot_unlock.py              — Normal boot: ask for passphrase, decrypt, seed
  boot_unlock.py encrypt      — Interactive: encrypt a token with a new passphrase
  boot_unlock.py test         — Verify the encrypted token can be decrypted
  boot_unlock.py rekey        — Re-encrypt with a new passphrase

Configuration:
  Edit the CONFIG section below to customize for your setup.
"""

import json
import os
import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────
# Edit these values to match your setup:

CONFIG = {
    # Telegram chat ID to send unlock requests to
    "chat_id": "YOUR_TELEGRAM_CHAT_ID",

    # Path to encrypted token file
    "encrypted_token_path": Path.home() / ".config" / "encrypted_token.enc",

    # Path to store decrypted token in tmpfs
    "tmpfs_token_path": Path("/dev/shm/decrypted-token"),

    # Path to config file containing bot token (JSON format)
    "config_path": Path.home() / ".config" / "config.json",

    # JSON path to bot token within config file
    # e.g. ["telegram", "bot_token"] reads config["telegram"]["bot_token"]
    "bot_token_path": ["telegram", "bot_token"],

    # System service name (for status messages)
    "service_name": "your-service",

    # Timing
    "poll_interval": 2,          # seconds between Telegram polls
    "reminder_interval": 1800,   # 30 minutes between reminders
    "max_attempts": 3,           # wrong passphrase attempts before cooldown
    "cooldown_seconds": 600,     # 10 minute cooldown after max attempts
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [boot_unlock] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("boot_unlock")


# ── Telegram API ───────────────────────────────────────────────────────────

def get_bot_token() -> str:
    """Read bot token from config file."""
    config_path = CONFIG["config_path"]
    if not config_path.exists():
        raise RuntimeError(f"Config file not found: {config_path}")

    data = json.loads(config_path.read_text())
    token = data
    for key in CONFIG["bot_token_path"]:
        if not isinstance(token, dict) or key not in token:
            raise RuntimeError(
                f"Bot token not found at path {'.'.join(CONFIG['bot_token_path'])}"
            )
        token = token[key]

    if not token:
        raise RuntimeError("Bot token is empty in config")
    return token


def telegram_api(bot_token: str, method: str, params: dict = None) -> dict:
    """Call Telegram Bot API."""
    import urllib.request
    import urllib.parse

    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def send_message(bot_token: str, text: str) -> Optional[int]:
    """Send a message to the configured chat. Returns message_id."""
    result = telegram_api(bot_token, "sendMessage", {
        "chat_id": CONFIG["chat_id"],
        "text": text,
        "parse_mode": "HTML",
    })
    return result["result"]["message_id"] if result.get("ok") else None


def delete_message(bot_token: str, message_id: int) -> bool:
    """Delete a message from Telegram."""
    try:
        result = telegram_api(bot_token, "deleteMessage", {
            "chat_id": CONFIG["chat_id"],
            "message_id": str(message_id),
        })
        return result.get("ok", False)
    except Exception:
        return False


def poll_for_reply(bot_token: str, after_message_id: int) -> Tuple[Optional[str], Optional[int]]:
    """Long-poll for a reply. Returns (text, message_id) or (None, None)."""
    offset = getattr(poll_for_reply, "_offset", None)
    params = {"timeout": "10", "allowed_updates": '["message"]'}
    if offset:
        params["offset"] = str(offset)

    try:
        result = telegram_api(bot_token, "getUpdates", params)
    except Exception as e:
        log.warning(f"Poll error: {e}")
        return None, None

    if not result.get("ok"):
        return None, None

    for update in result.get("result", []):
        poll_for_reply._offset = update["update_id"] + 1
        msg = update.get("message", {})
        if str(msg.get("chat", {}).get("id")) != CONFIG["chat_id"]:
            continue
        text = msg.get("text", "").strip()
        msg_id = msg.get("message_id")
        if text and msg_id:
            return text, msg_id

    return None, None


# ── Encryption ─────────────────────────────────────────────────────────────

def _openssl_with_passphrase(args: list, passphrase: str, **kwargs) -> subprocess.CompletedProcess:
    """
    Run openssl with passphrase via file descriptor (fd:N).

    More secure than pass:password because the passphrase doesn't appear
    in /proc/<pid>/cmdline and is only accessible to the process.
    """
    pass_read, pass_write = os.pipe()
    try:
        os.write(pass_write, passphrase.encode())
        os.close(pass_write)
        pass_write = -1
        return subprocess.run(
            args + ["-pass", f"fd:{pass_read}"],
            pass_fds=(pass_read,),
            capture_output=True,
            check=True,
            **kwargs,
        )
    finally:
        os.close(pass_read)
        if pass_write >= 0:
            os.close(pass_write)


def encrypt_token(token: str, passphrase: str) -> bytes:
    """Encrypt a token with AES-256-CBC via openssl."""
    result = _openssl_with_passphrase(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt"],
        passphrase,
        input=token.encode(),
    )
    return result.stdout


def decrypt_token(encrypted: bytes, passphrase: str) -> Optional[str]:
    """Decrypt a token. Returns None on wrong passphrase."""
    try:
        result = _openssl_with_passphrase(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-d"],
            passphrase,
            input=encrypted,
        )
        token = result.stdout.decode().strip()
        if len(token) > 10:  # Reasonable minimum length
            return token
        log.warning("Decrypted value seems too short")
        return None
    except subprocess.CalledProcessError:
        return None


def seed_to_tmpfs(token: str):
    """Write the decrypted token to tmpfs with restricted permissions."""
    path = CONFIG["tmpfs_token_path"]
    path.write_text(token)
    path.chmod(0o600)
    log.info(f"✅ Token seeded to {path}")


# ── Boot Flow ──────────────────────────────────────────────────────────────

def boot_unlock():
    """Main boot sequence: ask for passphrase, decrypt, seed."""
    encrypted_path = CONFIG["encrypted_token_path"]
    if not encrypted_path.exists():
        log.error(f"❌ Encrypted token not found: {encrypted_path}")
        log.error("Run: boot_unlock.py encrypt")
        sys.exit(1)

    encrypted = encrypted_path.read_bytes()
    bot_token = get_bot_token()

    # Wait for DNS (network-online.target doesn't guarantee it)
    log.info("Waiting for network...")
    for attempt in range(30):
        try:
            telegram_api(bot_token, "getMe")
            log.info("Network ready")
            break
        except Exception:
            if attempt < 29:
                time.sleep(2)
            else:
                log.error("❌ Network not available after 60s")
                sys.exit(1)

    # Drain old updates
    log.info("Draining old Telegram updates...")
    try:
        result = telegram_api(bot_token, "getUpdates", {"offset": "-1"})
        if result.get("ok") and result.get("result"):
            poll_for_reply._offset = result["result"][-1]["update_id"] + 1
    except Exception:
        pass

    # Send unlock request
    now = datetime.now().strftime("%H:%M %b %d")
    name = CONFIG["service_name"]
    prompt_id = send_message(bot_token,
        f"🔐 <b>{name} rebooted</b> ({now})\n\n"
        f"Send me the passphrase to unlock the vault.\n"
        f"I'll delete your message immediately after reading it."
    )
    log.info("Sent unlock request")

    attempts = 0
    last_reminder = time.time()

    while True:
        text, msg_id = poll_for_reply(bot_token, prompt_id)

        if text is None:
            if time.time() - last_reminder > CONFIG["reminder_interval"]:
                send_message(bot_token, f"🔐 Still waiting for passphrase to unlock {name}...")
                last_reminder = time.time()
            continue

        # Delete passphrase message immediately
        if msg_id:
            deleted = delete_message(bot_token, msg_id)
            log.info("Deleted passphrase message" if deleted else "⚠️ Could not delete message!")

        token = decrypt_token(encrypted, text)
        text = None  # Clear passphrase from memory

        if token:
            seed_to_tmpfs(token)
            send_message(bot_token, f"✅ Vault unlocked. {name} is starting up...")
            if prompt_id:
                delete_message(bot_token, prompt_id)
            log.info("✅ Unlock successful")
            return

        attempts += 1
        remaining = CONFIG["max_attempts"] - attempts
        if remaining > 0:
            send_message(bot_token,
                f"❌ Wrong passphrase. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )
            log.warning(f"Wrong passphrase (attempt {attempts}/{CONFIG['max_attempts']})")
        else:
            cooldown_min = CONFIG["cooldown_seconds"] // 60
            send_message(bot_token,
                f"🔒 Too many attempts. Cooling down for {cooldown_min} minutes."
            )
            log.warning(f"Cooldown: {cooldown_min} minutes")
            time.sleep(CONFIG["cooldown_seconds"])
            attempts = 0
            send_message(bot_token, f"🔐 Cooldown over. Send passphrase to unlock {name}.")
            last_reminder = time.time()


# ── CLI Commands ───────────────────────────────────────────────────────────

def cmd_encrypt():
    """Interactive: encrypt a token with a passphrase."""
    import getpass

    print("Enter the token to encrypt (will not be echoed):")
    token = getpass.getpass("Token: ").strip()
    if not token:
        print("❌ No token provided"); sys.exit(1)
    if len(token) < 10:
        print("⚠️  Token seems short — are you sure?")

    print(f"Token: {token[:20]}...")

    passphrase = getpass.getpass("Enter passphrase: ")
    confirm = getpass.getpass("Confirm passphrase: ")
    if passphrase != confirm:
        print("❌ Passphrases don't match"); sys.exit(1)
    if len(passphrase) < 6:
        print("❌ Passphrase too short (min 6 chars)"); sys.exit(1)

    encrypted = encrypt_token(token, passphrase)
    path = CONFIG["encrypted_token_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted)
    path.chmod(0o600)
    print(f"✅ Encrypted token saved to {path} ({len(encrypted)} bytes)")

    check = decrypt_token(encrypted, passphrase)
    if check == token:
        print("✅ Verification passed")
    else:
        print("❌ Verification FAILED!"); sys.exit(1)

    print("\nNext: set up systemd service, test with boot_unlock.py test, then reboot.")


def cmd_test():
    """Verify the encrypted token can be decrypted."""
    import getpass
    path = CONFIG["encrypted_token_path"]
    if not path.exists():
        print(f"❌ No encrypted token at {path}"); sys.exit(1)
    encrypted = path.read_bytes()
    passphrase = getpass.getpass("Enter passphrase: ")
    token = decrypt_token(encrypted, passphrase)
    if token:
        print(f"✅ Decryption successful: {token[:20]}...")
    else:
        print("❌ Wrong passphrase or corrupted file"); sys.exit(1)


def cmd_rekey():
    """Re-encrypt with a new passphrase."""
    import getpass
    path = CONFIG["encrypted_token_path"]
    if not path.exists():
        print(f"❌ No encrypted token at {path}"); sys.exit(1)

    encrypted = path.read_bytes()
    current = getpass.getpass("Current passphrase: ")
    token = decrypt_token(encrypted, current)
    if not token:
        print("❌ Wrong current passphrase"); sys.exit(1)

    new_pass = getpass.getpass("New passphrase: ")
    confirm = getpass.getpass("Confirm: ")
    if new_pass != confirm:
        print("❌ Don't match"); sys.exit(1)
    if len(new_pass) < 6:
        print("❌ Too short"); sys.exit(1)

    new_encrypted = encrypt_token(token, new_pass)
    path.write_bytes(new_encrypted)
    path.chmod(0o600)

    if decrypt_token(new_encrypted, new_pass) == token:
        print("✅ Re-keyed successfully")
    else:
        path.write_bytes(encrypted)  # Rollback
        print("❌ Verification failed — rolled back"); sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "boot"
    cmds = {"boot": boot_unlock, "encrypt": cmd_encrypt, "test": cmd_test, "rekey": cmd_rekey}
    if cmd in cmds:
        cmds[cmd]()
    else:
        print(f"Unknown: {cmd}")
        print("Usage: boot_unlock.py [boot|encrypt|test|rekey]")
        sys.exit(1)
