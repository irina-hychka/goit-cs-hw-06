"""
Minimal web app without frameworks.

- HTTP server (port 3000) serves:
    /               -> templates/index.html
    /message(.html) -> templates/message.html (form)
    /static/...     -> files under static/
  Any other path -> 404 with templates/error.html

- POST /submit forwards URL-encoded form data to a UDP socket server (port 5000).

- Socket server receives bytes, parses form fields, adds server-side timestamp,
  and stores documents to MongoDB:
    { "date": "YYYY-MM-DD HH:MM:SS.ffffff", "username": "...", "message": "..." }

Both servers are started from this file in separate processes.
"""

from __future__ import annotations

import mimetypes
import os
import socket
import sys
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from multiprocessing import Process
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# ----------------------- Configuration -----------------------

HTTP_HOST = "0.0.0.0"
HTTP_PORT = 3000

SOCKET_HOST = "0.0.0.0"
SOCKET_PORT = 5000  # UDP

# Mongo via env (matches docker-compose). Uses authSource=admin.
MONGO_URI = os.getenv("MONGO_URI", "mongodb://root:example@mongo:27017/?authSource=admin")
MONGO_DB = os.getenv("MONGO_DB", "messages_db")
MONGO_COLL = os.getenv("MONGO_COLL", "messages")

# Folders for HTML and static
TEMPLATES_DIR = Path("templates").resolve()
STATIC_DIR = Path("static").resolve()

# ----------------------- HTTP Server -------------------------


class SimpleHttpHandler(BaseHTTPRequestHandler):
    """Very small HTTP router + static file server."""

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        route = url.path

        try:
            # HTML pages
            if route in ("/", "/index.html"):
                return self._send_html_file(TEMPLATES_DIR / "index.html")
            if route in ("/message", "/message.html"):
                return self._send_html_file(TEMPLATES_DIR / "message.html")

            # Favicon (optional)
            if route == "/favicon.ico":
                icon = STATIC_DIR / "favicon.ico"
                return self._send_static_file(icon) if icon.exists() else self._send_404()

            # Static: /static/...
            if route.startswith("/static/"):
                rel = route[len("/static/") :]
                target = (STATIC_DIR / rel).resolve()
                if not _is_under(target, STATIC_DIR) or not target.is_file():
                    return self._send_404()
                return self._send_static_file(target)

            # Anything else → 404 page
            return self._send_404()
        except Exception:
            return self._send_404()

    def do_POST(self) -> None:
        """Receive form data from /message.html and forward to the UDP socket server."""
        if self.path != "/submit":
            return self._send_404()

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)  # raw URL-encoded bytes

        # Forward as-is to UDP socket server
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(body, (SOCKET_HOST, SOCKET_PORT))
        except socket.error as exc:
            sys.stderr.write(f"[HTTP] UDP forward failed: {exc}\n")

        # Redirect back
        self.send_response(HTTPStatus.SEE_OTHER) # 303 See Other
        self.send_header("Location", "/message.html?status=ok")
        self.end_headers()

    # ----------------- Helpers -----------------

    def _send_html_file(self, path: Path, status: int = 200) -> None:
        """Send an HTML file (index/message/error)."""
        if not path.exists() or not path.is_file():
            return self._send_404()

        content = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_static_file(self, path: Path, status: int = 200) -> None:
        """Send CSS/PNG/etc. using mimetypes."""
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        self.send_response(status)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_404(self) -> None:
        """Serve error.html with 404 status (safe fallback)."""
        try:
            error_page = TEMPLATES_DIR / "error.html"
            if error_page.exists():
                return self._send_html_file(error_page, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            sys.stderr.write(f"[HTTP] 404 page failed, fallback to text: {exc}\n")

        msg = b"404 Not Found"
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    # Quieter logs
    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        sys.stderr.write(f"[HTTP] {self.address_string()} - {fmt % args}\n")


def _is_under(child: Path, parent: Path) -> bool:
    """Return True if 'child' path is inside 'parent' (prevents path traversal)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def run_http_server() -> None:
    """Start HTTP server on port 3000."""
    if not TEMPLATES_DIR.exists():
        sys.stderr.write(f"[HTTP] templates dir not found: {TEMPLATES_DIR}\n")
    if not STATIC_DIR.exists():
        sys.stderr.write(f"[HTTP] static dir not found: {STATIC_DIR}\n")

    server = HTTPServer((HTTP_HOST, HTTP_PORT), SimpleHttpHandler)
    print(f"[HTTP] listening on http://{HTTP_HOST}:{HTTP_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ----------------------- UDP Socket Server -------------------


def run_socket_server() -> None:
    """
    UDP socket server on port 5000.

    Receives URL-encoded form data, parses into dict,
    attaches server-side timestamp, and inserts into MongoDB.
    """
    # One Mongo client per process (faster than per-message).
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command("ping")  # fail fast if auth wrong
        mongo_coll = mongo_client[MONGO_DB][MONGO_COLL]
        print(f"[SOCKET] Connected to MongoDB: {MONGO_URI}")
    except ConnectionFailure as exc:
        print(f"[SOCKET] Mongo connection failed: {exc}")
        return
    except Exception as exc:
        print(f"[SOCKET] Mongo init error: {exc}")
        return

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((SOCKET_HOST, SOCKET_PORT))
        print(f"[SOCKET] UDP listening on {SOCKET_HOST}:{SOCKET_PORT}")

        while True:
            data, addr = sock.recvfrom(65535)
            decoded = data.decode("utf-8", errors="ignore")
            print(f"[SOCKET] received from {addr}: {decoded!r}")

            # Parse URL-encoded body safely
            parsed = urllib.parse.parse_qs(decoded, keep_blank_values=True)
            username = parsed.get("username", [""])[0].strip()
            message = parsed.get("message", [""])[0].strip()

            # Build document with server-side timestamp
            doc = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                "username": username,
                "message": message,
            }

            if doc["username"] and doc["message"]:
                try:
                    mongo_coll.insert_one(doc)
                    print(f"[SOCKET] saved: {doc!r}")
                except Exception as exc:
                    print(f"[SOCKET] Mongo insert error: {exc}")
            else:
                print("[SOCKET] Skipped insert: empty username or message")


# ----------------------- Entry Point -------------------------


if __name__ == "__main__":
    http_proc = Process(target=run_http_server)
    socket_proc = Process(target=run_socket_server)

    http_proc.start()
    socket_proc.start()

    http_proc.join()
    socket_proc.join()
