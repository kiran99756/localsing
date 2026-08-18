"""
discovery.py
------------
A second, more bulletproof auto-discovery path alongside the existing
QR code + mDNS (localshare.local).

WHY THIS EXISTS:
mDNS (.local names) is what powers the QR/hostname discovery already in
main.py, but it's not 100% reliable in practice - some routers block
multicast, some Android phones' browsers don't resolve .local at all,
and public/guest Wi-Fi often isolates clients from each other's mDNS
traffic. UDP broadcast discovery is a simpler, more universally-supported
fallback: "is anyone running Local Share on this network?" / "yes, I'm
at 192.168.1.42:8000".

This is primarily useful for:
- A future companion app (Android/desktop) that can send a real UDP
  packet - something a plain web browser cannot do.
- Power users on a laptop who'd rather run a 5-line discovery script
  than hunt for an IP address.

PROTOCOL (deliberately tiny):
  Client broadcasts the ASCII text  b"LOCALSHARE_DISCOVER"  to
  <broadcast>:37020 (UDP).
  Server replies (unicast, straight back to the sender) with a JSON
  payload: {"app": "localshare", "name": "...", "ip": "...", "port": 8000}

No auth on this beacon by design - it only reveals "a Local Share server
exists at this IP", not any file contents or the password. Same threat
model as mDNS/the QR code, which are equally unauthenticated by nature.
"""

import json
import socket
import threading

import config


def _get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


_beacon_socket: socket.socket | None = None
_beacon_thread: threading.Thread | None = None
_stop_flag = threading.Event()


def _listen_loop(server_name: str):
    global _beacon_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", config.DISCOVERY_PORT))
    except OSError as e:
        print(f"[discovery] Could not bind UDP port {config.DISCOVERY_PORT}: {e}")
        return
    sock.settimeout(1.0)  # so we can check _stop_flag periodically instead of blocking forever
    _beacon_socket = sock
    print(f"[discovery] Listening for auto-discovery broadcasts on UDP {config.DISCOVERY_PORT}")

    while not _stop_flag.is_set():
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except OSError:
            break

        if data == b"LOCALSHARE_DISCOVER":
            reply = json.dumps({
                "app": "localshare",
                "name": server_name,
                "ip": _get_lan_ip(),
                "port": config.APP_PORT,
            }).encode()
            try:
                sock.sendto(reply, addr)
            except OSError:
                pass

    sock.close()


def start(server_name: str = "Local Share"):
    """Call once at app startup. Runs the listener in a background thread."""
    global _beacon_thread
    _stop_flag.clear()
    _beacon_thread = threading.Thread(target=_listen_loop, args=(server_name,), daemon=True)
    _beacon_thread.start()


def stop():
    """Call at app shutdown to release the UDP port cleanly."""
    _stop_flag.set()
    if _beacon_socket:
        try:
            _beacon_socket.close()
        except OSError:
            pass
