# Build & Setup Requirements

This covers everything needed to run, build, or package Local Share, across
its four ways of being used.

## 1. Running it normally (dev / any OS)

**Requirements:**
- Python 3.10 or newer
- `pip install -r requirements.txt`

```bash
git clone https://github.com/YOUR_USERNAME/local-share.git
cd local-share
pip install -r requirements.txt
python main.py
```

No other setup needed. First run auto-generates `security.json` (password +
encryption key) and prints the password + a join URL/QR code.

## 2. Building the Windows `.exe`

**Requirements (on the Windows machine doing the build):**
- Python 3.10+ (only needed to *build* — not needed to *run* the resulting .exe)
- `pip install -r requirements-build.txt` (this is `requirements.txt` + PyInstaller)

```
build_windows.bat
```

This creates a venv, installs `requirements-build.txt`, and runs
`pyinstaller localshare.spec`. Output: `dist\LocalShare.exe` — a single
file, no Python required on whatever machine you copy it to.

**Or let GitHub build it for you:** push a tag like `v1.0.0` and the
`.github/workflows/build-exe.yml` Actions workflow builds it on a real
Windows runner and attaches it to a GitHub Release automatically.

## 3. Internet Sharing feature (optional, one-time)

**Requirement:** the `cloudflared` binary — NOT a Python package, a small
standalone executable from Cloudflare.

- Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
- No Cloudflare account needed for the quick-tunnel mode this app uses.
- Install once, it just needs to be on your system `PATH`; the app calls it
  as a subprocess when you click "Share Over the Internet".
- If it's missing, the app shows an in-page error with the same install
  link rather than crashing.

## 4. Installing as an Android app (PWA)

**Requirement:** none beyond a Chrome-based browser on Android — the
manifest + service worker are already part of the app (`static/manifest.json`,
`static/service-worker.js`).

- Open the site on your phone, then Chrome menu → **Add to Home Screen**.
- Note: Chrome only grants the *full* standalone-app experience (no
  browser chrome, proper install prompt) over HTTPS or `localhost`. Plain
  LAN `http://` still adds a working home-screen icon, just opening in a
  normal browser tab. The Internet Sharing link (#3) is HTTPS, so
  installing from that link gets the full experience.

## Version summary

| What | Needs |
|---|---|
| Run the server | Python 3.10+, `requirements.txt` |
| Build Windows `.exe` | Python 3.10+, `requirements-build.txt`, PyInstaller |
| Internet sharing | `cloudflared` binary (one-time, system-wide) |
| Android install | Nothing extra — built into the app already |

Note: dependency version floors in `requirements.txt`/`requirements-build.txt`
are based on known-compatible releases, not verified against a live install in
this environment (this sandbox has no network access to run `pip install`) —
if you hit a version conflict on your machine, drop the `>=` pin for that one
package and let pip resolve it.
