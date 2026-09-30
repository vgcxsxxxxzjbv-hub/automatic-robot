import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests

import bot.db as db
from bot.config import BOT_TOKEN


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "file":
            self.send_response(404); self.end_headers(); return
        sid = parts[1]
        row = db.get_file(sid)
        if not row:
            self.send_response(404); self.end_headers()
            self.wfile.write(b"File not found"); return
        db.inc_views(sid)
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": row["file_id"]},
            timeout=10,
        ).json()
        if not r.get("ok"):
            self.send_response(500); self.end_headers(); return
        direct = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{r['result']['file_path']}"
        self.send_response(302)
        self.send_header("Location", direct)
        self.end_headers()
