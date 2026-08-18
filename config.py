"""
config.py
---------
Shared setup for paths + security (login password, session signing,
file encryption). Split out from main.py so database.py can import
the data-folder path without a circular import, and so PyInstaller
packaging concerns live in one place.

WHY PASSWORD AND ENCRYPTION KEY ARE STORED SEPARATELY:
The site password is what people type to get in - you might want to
change it later (new event, new group of people). The encryption key
is what scrambles files on disk. If the encryption key were derived
from the password, changing the password would make every previously
uploaded file undecryptable. So instead: a random encryption key is
generated once and saved locally, and the password is just checked
against a saved value. Change the password freely; old files still open.
"""

import os
import sys
import json
import secrets
import hmac
import hashlib

from cryptography.fernet import Fernet

APP_PORT = int(os.environ.get("PORT", 8000))   # Railway (and most PaaS hosts) inject PORT
DISCOVERY_PORT = 37020     # UDP port the auto-discovery beacon listens on (LAN-only; harmless no-op on cloud hosts)

# On Railway, RAILWAY_PUBLIC_DOMAIN is auto-set to the app's public hostname
# (no port needed - Railway terminates HTTPS on 443 and forwards to PORT).
# Used instead of the LAN-IP QR code/join-URL when running there.
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
PUBLIC_URL = f"https://{_railway_domain}" if _railway_domain else None


def _app_dir() -> str:
    """
    Folder the app's WRITABLE data (uploads/, database, security.json)
    lives in.
    - LOCALSHARE_DATA_DIR env var, if set: used as-is. This is how a
      Railway (or any container host) Volume gets used instead of the
      container's own ephemeral filesystem - without it, uploads and
      security.json would vanish on every redeploy.
    - Normal `python main.py`: the folder this file is in.
    - Packaged Windows .exe (PyInstaller --onefile): the folder the
      .exe itself sits in - NOT the temporary _MEIPASS folder, which
      is wiped after every run and would lose all uploads/keys.
    """
    env_dir = os.environ.get("LOCALSHARE_DATA_DIR")
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir(*parts) -> str:
    """
    Folder READ-ONLY bundled assets (templates/, static/) live in.
    Same as _app_dir() when running normally, but points inside
    PyInstaller's extracted bundle when frozen.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


DATA_DIR = _app_dir()
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "filesharing.db")
SECURITY_FILE = os.path.join(DATA_DIR, "security.json")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _load_or_create_security() -> dict:
    """
    First run ever: generate a password (or take one from the
    LOCALSHARE_PASSWORD environment variable), a random secret for
    signing session cookies, and a random encryption key - then save
    all three to security.json so restarts don't lock everyone out
    or make old files unreadable.

    Later runs: reuse what's saved. If LOCALSHARE_PASSWORD is set in
    the environment, it overrides the saved password (lets you rotate
    the password without deleting security.json), but the signing
    secret and encryption key are always kept stable.
    """
    if os.path.exists(SECURITY_FILE):
        with open(SECURITY_FILE, "r") as f:
            data = json.load(f)
        env_password = os.environ.get("LOCALSHARE_PASSWORD")
        if env_password:
            data["password"] = env_password
        return data

    data = {
        "password": os.environ.get("LOCALSHARE_PASSWORD") or secrets.token_urlsafe(6),
        "cookie_secret": secrets.token_hex(32),
        "encryption_key": Fernet.generate_key().decode(),
    }
    with open(SECURITY_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return data


_security = _load_or_create_security()

APP_PASSWORD: str = _security["password"]
_COOKIE_SECRET: str = _security["cookie_secret"]
FERNET = Fernet(_security["encryption_key"].encode())

# The session cookie's value: a constant HMAC signature, so a browser
# can only produce/guess it by having read this file (or logging in
# and receiving it from the server). Stable across restarts since
# _COOKIE_SECRET is persisted, so people don't get logged out just
# because the server restarted.
SESSION_TOKEN: str = hmac.new(
    _COOKIE_SECRET.encode(), b"authenticated", hashlib.sha256
).hexdigest()


def check_password(candidate: str) -> bool:
    """Constant-time password comparison (avoids leaking timing info)."""
    return hmac.compare_digest(candidate, APP_PASSWORD)


# ---------------------------------------------------------------------------
# File encryption helpers
# ---------------------------------------------------------------------------
# Every file written to uploads/ is run through Fernet (AES-128-CBC +
# HMAC-SHA256, from the `cryptography` package) before it touches disk.
# That means anyone who copies the raw uploads/ folder - a stolen laptop,
# a cloud backup, another user account on the same PC - gets unreadable
# bytes without security.json's encryption_key.
#
# Trade-off: Fernet ciphertext isn't seekable, so a file has to be fully
# decrypted before it can be served. For downloads that's invisible. For
# previewing video/images, main.py decrypts once into a short-lived temp
# file (see TMP_PREVIEW_DIR) so the browser can still seek/scrub normally.

def encrypt_bytes(data: bytes) -> bytes:
    return FERNET.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return FERNET.decrypt(token)


TMP_PREVIEW_DIR = os.path.join(DATA_DIR, ".preview_cache")
os.makedirs(TMP_PREVIEW_DIR, exist_ok=True)
