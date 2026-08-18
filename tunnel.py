"""
tunnel.py
---------
Optional "Share over the Internet" feature.

By default Local Share only works on your local Wi-Fi - that's the whole
point of the name, and it's why there's no need for HTTPS/rate-limiting/etc.
But sometimes you want one friend who ISN'T on your Wi-Fi to grab a file.

Rather than asking you to configure port forwarding on your router (a real
security foot-gun - it opens your home network to the whole internet), this
uses a Cloudflare "quick tunnel": Cloudflare's `cloudflared` binary opens an
outbound-only connection to Cloudflare's edge and hands you a temporary
public HTTPS URL like `https://random-words.trycloudflare.com` that proxies
straight back to your local server. Nothing is opened on your router/firewall,
and the URL stops working the moment you stop the tunnel.

REQUIRES the `cloudflared` binary to be installed once on the host machine
(NOT a Python package - a small standalone executable from Cloudflare).
If it isn't installed, start_tunnel() raises FileNotFoundError with
install instructions; main.py turns that into a friendly error message
in the UI rather than a crash.

Your Local Share password still applies over this URL - anyone with the
link still has to log in, same as on the LAN.
"""

import os
import re
import shutil
import subprocess
import threading

import config

_process: subprocess.Popen | None = None
_public_url: str | None = None
_lock = threading.Lock()

_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")

INSTALL_HINT = (
    "cloudflared isn't installed. Install it once from "
    "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ "
    "(no Cloudflare account needed for this quick-tunnel mode), then try again."
)

# Common install locations that DON'T end up on PATH automatically - e.g.
# some Windows installers drop cloudflared.exe into Program Files without
# ever touching the user's PATH. Checked in order after the PATH lookup.
_COMMON_LOCATIONS = [
    r"C:\Program Files\cloudflared\cloudflared.exe",
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\cloudflared\cloudflared.exe",
    "/usr/local/bin/cloudflared",
    "/opt/homebrew/bin/cloudflared",
    "/usr/bin/cloudflared",
]


def find_cloudflared() -> str | None:
    """
    Locates the cloudflared binary without assuming it's on PATH.
    Checks, in order: LOCALSHARE_CLOUDFLARED env var override, PATH
    (via shutil.which), then a handful of known install locations that
    some installers use without registering PATH (e.g. Program Files
    on Windows).
    """
    override = os.environ.get("LOCALSHARE_CLOUDFLARED")
    if override and os.path.isfile(override):
        return override

    on_path = shutil.which("cloudflared")
    if on_path:
        return on_path

    for candidate in _COMMON_LOCATIONS:
        if os.path.isfile(candidate):
            return candidate

    return None


def _read_output(proc: subprocess.Popen):
    global _public_url
    for line in proc.stderr:  # cloudflared logs the URL to stderr
        match = _URL_PATTERN.search(line)
        if match:
            with _lock:
                _public_url = match.group(0)
            break


def start_tunnel():
    """
    Launches `cloudflared tunnel --url http://localhost:<port>` in the
    background and starts a thread that watches its output for the
    assigned public URL. Call get_status() afterwards to poll for it -
    it typically takes 2-5 seconds to appear.
    """
    global _process, _public_url
    with _lock:
        if _process is not None:
            return  # already running
        _public_url = None

    binary = find_cloudflared()
    if binary is None:
        raise FileNotFoundError(INSTALL_HINT)

    try:
        proc = subprocess.Popen(
            [binary, "tunnel", "--url", f"http://localhost:{config.APP_PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        raise FileNotFoundError(INSTALL_HINT)

    with _lock:
        _process = proc

    threading.Thread(target=_read_output, args=(proc,), daemon=True).start()


def get_status() -> dict:
    with _lock:
        active = _process is not None and _process.poll() is None
        return {"active": active, "url": _public_url, "starting": active and _public_url is None}


def stop_tunnel():
    global _process, _public_url
    with _lock:
        proc, _process = _process, None
        _public_url = None
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
