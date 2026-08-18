"""
main.py
-------
The server. Explained section by section with comments.

KEY IDEA - "Device Name" instead of Login:
Instead of usernames/passwords PER PERSON, each browser picks a display
name once and it's remembered in a browser cookie - that's just "who did
what", not security. Actual security (keeping strangers off your network
share) is a SINGLE shared password for the whole app, checked once per
browser (see config.py + /login below), plus encrypting every file at
rest so the uploads/ folder is useless without the app's key.
"""

import hashlib
import json
import mimetypes
import os
import shutil
import socket
import uuid

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import qrcode

import config
import database
import discovery
import tunnel

# Zeroconf/mDNS - lets other devices find this server by name (localshare.local)
# instead of typing an IP address. This is the real protocol behind "just works"
# discovery features like AirDrop. It's optional: if the package isn't installed,
# the app still runs fine, just without name-based discovery.
try:
    from zeroconf import ServiceInfo, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

app = FastAPI()

# UPLOAD_FOLDER / DB_PATH live under config.DATA_DIR - the folder next to
# main.py when run normally, or next to the .exe when packaged. static/ and
# templates/ are read via config.resource_dir(), which points inside the
# PyInstaller bundle when frozen instead.
UPLOAD_FOLDER = config.UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

database.init_db()  # creates filesharing.db + the files table if not already there

STATIC_DIR = config.resource_dir("static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=config.resource_dir("templates"))


def get_lan_ip() -> str:
    """
    Find this machine's real LAN IP (not 127.0.1.1).
    Trick: open a UDP 'connection' to a public IP - no data is actually sent,
    but the OS is forced to pick which network interface it WOULD use,
    and we read that interface's address.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# QR code + preview cache are regenerated/written into config.DATA_DIR
# (writable) rather than the static/ folder, since static/ lives inside the
# read-only PyInstaller bundle when the app is packaged as an .exe.
QR_PATH = os.path.join(config.DATA_DIR, "qr.png")


def generate_qr():
    url = config.PUBLIC_URL or f"http://{get_lan_ip()}:{config.APP_PORT}"
    qrcode.make(url).save(QR_PATH)


generate_qr()

MDNS_HOSTNAME = "localshare"  # devices can reach this at http://localshare.local:8000
_zeroconf_instance = None


def register_mdns():
    """
    Announce this server on the local network as 'localshare.local' using mDNS
    (multicast DNS) - the same family of protocol Apple's Bonjour/AirDrop and
    Android's local network discovery use. Once registered, other devices on
    the same Wi-Fi can reach the server by name instead of typing its IP.

    Works out of the box on macOS, Linux, iOS, and most Android phones.
    Windows PCs may need "Bonjour Print Services" (a free Apple download)
    installed for .local names to resolve.
    """
    global _zeroconf_instance
    if not ZEROCONF_AVAILABLE:
        print("[mDNS] 'zeroconf' package not installed - skipping local-name discovery.")
        print("[mDNS] Install with: pip install zeroconf")
        return

    ip = get_lan_ip()
    try:
        info = ServiceInfo(
            "_http._tcp.local.",
            f"{MDNS_HOSTNAME}._http._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=config.APP_PORT,
            server=f"{MDNS_HOSTNAME}.local.",
        )
        _zeroconf_instance = Zeroconf()
        _zeroconf_instance.register_service(info)
        print(f"[mDNS] Registered as http://{MDNS_HOSTNAME}.local:8000")
    except Exception as e:
        print(f"[mDNS] Could not register: {e}")


register_mdns()
discovery.start()


def safe_path(filename: str) -> str:
    """
    Security check: makes sure a filename can never escape the uploads/ folder,
    e.g. someone requesting /delete/../main.py
    """
    name = os.path.basename(filename)
    if name in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.abspath(os.path.join(UPLOAD_FOLDER, name))
    if os.path.commonpath([path, UPLOAD_FOLDER]) != UPLOAD_FOLDER:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def human_size(num_bytes: int) -> str:
    """Turn 1536000 into '1.5 MB' etc, for display."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


PREVIEWABLE_IMAGE = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}
PREVIEWABLE_VIDEO = {"mp4", "webm", "mov", "m4v", "ogg"}


def file_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# ---------------------------------------------------------------------------
# Auth - one shared password for the whole app (see config.py). A signed
# session cookie (config.SESSION_TOKEN) is set on successful login and
# checked on every page/API route below via the `require_auth` dependency.
# ---------------------------------------------------------------------------

def is_authenticated(session: str | None = Cookie(default=None)) -> bool:
    return session is not None and session == config.SESSION_TOKEN


def require_auth(request: Request, session: str | None = Cookie(default=None)):
    """
    Dependency used on every protected route. Browsers get redirected to the
    login page; API/XHR calls (Accept: application/json, or fetch/XHR from
    our own JS) get a clean 401 instead of an HTML redirect body.
    """
    if session == config.SESSION_TOKEN:
        return True
    wants_json = "application/json" in request.headers.get("accept", "")
    if wants_json or request.headers.get("x-requested-with") == "XMLHttpRequest":
        raise HTTPException(status_code=401, detail="Not authenticated")
    raise HTTPException(status_code=303, headers={"Location": "/login"})


@app.exception_handler(HTTPException)
async def redirect_on_303(request: Request, exc: HTTPException):
    if exc.status_code == 303 and "Location" in (exc.headers or {}):
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request.cookies.get("session")):
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if config.check_password(password):
        response = RedirectResponse(url="/", status_code=303)
        # Session cookie lasts a year so people don't get logged out just
        # because the server restarted (SESSION_TOKEN is stable across
        # restarts - see config.py).
        response.set_cookie(
            key="session", value=config.SESSION_TOKEN,
            max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": "Incorrect password - try again."},
        status_code=401,
    )


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    search: str = "",
    device_name: str | None = Cookie(default=None),
    _auth: bool = Depends(require_auth),
):
    files = database.get_all_files(search=search)
    for f in files:
        f["size_display"] = human_size(f["size_bytes"])
        ext = file_ext(f["filename"])
        f["is_image"] = ext in PREVIEWABLE_IMAGE
        f["is_video"] = ext in PREVIEWABLE_VIDEO

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "files": files,
            "search": search,
            "device_name": device_name or "",
            "mdns_hostname": MDNS_HOSTNAME,
            "mdns_active": ZEROCONF_AVAILABLE,
        },
    )


@app.get("/qr.png")
async def qr_image(_auth: bool = Depends(require_auth)):
    return FileResponse(QR_PATH)


@app.get("/discover")
async def discover():
    """
    Unauthenticated on purpose: it only announces "a Local Share server is
    here", not any file contents or the password - same information the
    QR code / mDNS name already broadcast to anyone on the LAN. Lets a
    network-scanning client (or a future companion app) confirm it found
    the right device among several IPs, as a fallback next to the UDP
    beacon in discovery.py.
    """
    return {"app": "localshare", "name": MDNS_HOSTNAME, "port": config.APP_PORT}


# ---------------------------------------------------------------------------
# Internet sharing (optional) - see tunnel.py for how this works and why
# ---------------------------------------------------------------------------

INTERNET_QR_PATH = os.path.join(config.DATA_DIR, "internet_qr.png")


@app.post("/internet-share/start")
async def internet_share_start(_auth: bool = Depends(require_auth)):
    try:
        tunnel.start_tunnel()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "starting"}


@app.get("/internet-share/status")
async def internet_share_status(_auth: bool = Depends(require_auth)):
    status = tunnel.get_status()
    if status["url"]:
        qrcode.make(status["url"]).save(INTERNET_QR_PATH)
    return status


@app.post("/internet-share/stop")
async def internet_share_stop(_auth: bool = Depends(require_auth)):
    tunnel.stop_tunnel()
    return {"status": "stopped"}


@app.get("/internet-qr.png")
async def internet_qr_image(_auth: bool = Depends(require_auth)):
    if not os.path.exists(INTERNET_QR_PATH):
        raise HTTPException(status_code=404, detail="Internet sharing isn't active")
    return FileResponse(INTERNET_QR_PATH)


@app.on_event("shutdown")
def cleanup_mdns():
    """Properly withdraw the mDNS announcement when the server stops."""
    if _zeroconf_instance:
        _zeroconf_instance.unregister_all_services()
        _zeroconf_instance.close()
    discovery.stop()
    tunnel.stop_tunnel()
    shutil.rmtree(config.TMP_PREVIEW_DIR, ignore_errors=True)


@app.post("/set-device-name")
async def set_device_name(request: Request, _auth: bool = Depends(require_auth)):
    """
    Called once from the browser the first time someone visits, or whenever
    they change their display name. Stores it as a cookie so future visits
    (and uploads/chat messages) know who's who - no per-person password.
    """
    data = await request.json()
    name = data.get("name", "").strip()[:30]  # cap length to keep things sane
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    response = JSONResponse({"ok": True, "name": name})
    response.set_cookie(key="device_name", value=name, max_age=60 * 60 * 24 * 365)
    return response


# ---------------------------------------------------------------------------
# Upload / Download / Delete / Rename
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    device_name: str | None = Cookie(default=None),
    _auth: bool = Depends(require_auth),
):
    uploader = device_name or "Unknown device"
    filename = os.path.basename(file.filename)

    # Avoid overwriting an existing file with the same name
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{uuid.uuid4().hex[:6]}{ext}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)

    # Read the whole upload into memory, encrypt it, THEN write to disk -
    # so the bytes that ever touch the filesystem are already ciphertext.
    # (Fine for a small local-network sharing app; very large files could
    # be chunked/streamed instead, at the cost of more complex code.)
    raw = await file.read()
    encrypted = config.encrypt_bytes(raw)
    with open(file_path, "wb") as buffer:
        buffer.write(encrypted)

    size_bytes = len(raw)  # store the real (decrypted) size for display
    database.add_file_record(filename, uploader, size_bytes)

    await broadcast_system_message(f"{uploader} shared a file: {filename}")
    await broadcast_refresh()

    return {"message": "File uploaded successfully", "filename": filename}


@app.get("/download/{filename}")
async def download(filename: str, _auth: bool = Depends(require_auth)):
    file_path = safe_path(filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(file_path, "rb") as f:
        decrypted = config.decrypt_bytes(f.read())
    database.increment_download_count(os.path.basename(file_path))
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{os.path.basename(file_path)}"'}
    return Response(content=decrypted, media_type=media_type, headers=headers)


@app.get("/preview/{filename}")
async def preview(filename: str, _auth: bool = Depends(require_auth)):
    """
    Serves images/video decrypted for inline viewing (no download prompt).
    Fernet ciphertext can't be decrypted partially, so we decrypt once into
    a small temp-cache file under config.TMP_PREVIEW_DIR and hand THAT to
    FileResponse, which natively supports HTTP Range requests - needed for
    video scrubbing/seeking to work in the browser. The temp copy is
    content-addressed (named by a hash of the encrypted bytes) so repeat
    previews are instant and don't re-decrypt every time.
    """
    ext = file_ext(filename)
    if ext not in PREVIEWABLE_IMAGE and ext not in PREVIEWABLE_VIDEO:
        raise HTTPException(status_code=415, detail="File type not previewable")

    file_path = safe_path(filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    with open(file_path, "rb") as f:
        ciphertext = f.read()
    cache_name = hashlib.sha256(ciphertext[:4096] + filename.encode()).hexdigest() + "." + ext
    cache_path = os.path.join(config.TMP_PREVIEW_DIR, cache_name)

    if not os.path.exists(cache_path):
        decrypted = config.decrypt_bytes(ciphertext)
        tmp_path = cache_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(decrypted)
        os.replace(tmp_path, cache_path)

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(cache_path, media_type=media_type)


@app.post("/rename/{filename}")
async def rename(
    filename: str,
    new_name: str = Form(...),
    device_name: str | None = Cookie(default=None),
    _auth: bool = Depends(require_auth),
):
    old_path = safe_path(filename)
    if not os.path.isfile(old_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Keep the extension - renaming shouldn't change how a file is opened.
    old_ext = os.path.splitext(filename)[1]
    cleaned = os.path.basename(new_name).strip()
    cleaned = os.path.splitext(cleaned)[0] if os.path.splitext(cleaned)[1] else cleaned
    if not cleaned:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    new_filename = f"{cleaned}{old_ext}"
    new_path = safe_path(new_filename)

    if new_filename != filename and os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="A file with that name already exists")

    os.rename(old_path, new_path)
    database.rename_file_record(filename, new_filename)

    await broadcast_system_message(f"{device_name or 'Someone'} renamed {filename} -> {new_filename}")
    await broadcast_refresh()
    return {"message": "Renamed", "filename": new_filename}


@app.post("/delete/{filename}")
async def delete(filename: str, device_name: str | None = Cookie(default=None), _auth: bool = Depends(require_auth)):
    file_path = safe_path(filename)
    if os.path.isfile(file_path):
        os.remove(file_path)
        database.delete_file_record(os.path.basename(file_path))
        await broadcast_system_message(f"{device_name or 'Someone'} deleted a file: {filename}")
        await broadcast_refresh()
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Live chat (WebSocket) - now with usernames + an online-users list
# ---------------------------------------------------------------------------
# We send JSON messages instead of plain text, e.g.:
#   {"type": "chat", "user": "Rahul's Phone", "text": "hello"}
#   {"type": "system", "text": "Rahul's Phone shared a file: notes.pdf"}
#   {"type": "refresh"}
#   {"type": "presence", "users": ["Rahul's Phone", "Priya's Laptop"]}

connected_clients: dict[WebSocket, str] = {}  # maps each connection -> device name


async def broadcast(payload: dict):
    dead = []
    message = json.dumps(payload)
    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            dead.append(client)
    for client in dead:
        connected_clients.pop(client, None)


async def broadcast_refresh():
    await broadcast({"type": "refresh"})


async def broadcast_system_message(text: str):
    await broadcast({"type": "system", "text": text})


async def broadcast_presence():
    await broadcast({"type": "presence", "users": list(set(connected_clients.values()))})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, device_name: str | None = Cookie(default=None), session: str | None = Cookie(default=None)):
    if session != config.SESSION_TOKEN:
        await websocket.close(code=4401)  # custom code: not authenticated
        return

    await websocket.accept()
    name = device_name or "Unknown device"
    connected_clients[websocket] = name
    await broadcast_presence()
    await broadcast_system_message(f"{name} joined")

    try:
        while True:
            raw = await websocket.receive_text()
            await broadcast({"type": "chat", "user": name, "text": raw})
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.pop(websocket, None)
        await broadcast_presence()
        await broadcast_system_message(f"{name} left")


# ---------------------------------------------------------------------------
# Entry point - lets this run two ways:
#   1) `uvicorn main:app --reload` during development (hot reload)
#   2) `python main.py` / the packaged Windows .exe, which calls uvicorn
#      programmatically so double-clicking LocalShare.exe just works with
#      no terminal command needed.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = config.APP_PORT
    print("=" * 60)
    print("  Local Share")
    print(f"  Password: {config.APP_PASSWORD}")
    if config.PUBLIC_URL:
        print(f"  Public URL:       {config.PUBLIC_URL}")
    else:
        print(f"  Open on this PC:  http://localhost:{port}")
        print(f"  Open on phones:   http://{get_lan_ip()}:{port}  (or scan the QR code)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
