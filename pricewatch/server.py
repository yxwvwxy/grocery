"""Tiny local web server for the price dashboard (stdlib only)."""
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import STORES, db
from .cli import record_and_alert

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        conn = db.connect()
        try:
            if path == "/api/items":
                return self._json({"stores": STORES, "items": db.list_items(conn)})
            if path.startswith("/api/history/"):
                return self._json(db.history(conn, int(path.rsplit("/", 1)[1])))
        finally:
            conn.close()
        if path in ("/", "/index.html"):
            body = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        conn = db.connect()
        try:
            data = self._body()
            if path == "/api/items":
                if data.get("store") not in STORES or not data.get("name"):
                    return self._json({"error": "需要商品名和超市"}, 400)
                item_id = db.add_item(
                    conn, data["name"].strip(), data["store"], data.get("url") or None,
                    data.get("unit") or None, _num(data.get("target_price")),
                )
                price = _num(data.get("price"))
                if price is not None:
                    record_and_alert(conn, item_id, price, "manual")
                return self._json({"id": item_id})
            if path == "/api/prices":
                price = _num(data.get("price"))
                if price is None or not db.get_item(conn, int(data["item_id"])):
                    return self._json({"error": "价格或商品无效"}, 400)
                alerts = record_and_alert(conn, int(data["item_id"]), price, "manual", data.get("note") or None)
                return self._json({"alerts": alerts})
            if path.startswith("/api/items/") and path.endswith("/delete"):
                db.remove_item(conn, int(path.split("/")[3]))
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        finally:
            conn.close()


def _num(v):
    if v in (None, ""):
        return None
    return float(v)


def serve(port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:{}/".format(port)
    print("看板已启动: {}  (Ctrl+C 退出)".format(url))
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
