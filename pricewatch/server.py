"""Tiny local web server for the price comparison dashboard (stdlib only)."""
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
            if path == "/api/products":
                return self._json({"stores": STORES, "products": db.overview(conn)})
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
            if path == "/api/products":
                name, unit = (data.get("name") or "").strip(), (data.get("unit") or "").strip()
                if not name or not unit:
                    return self._json({"error": "English name and unit are required"}, 400)
                pid = db.add_product(
                    conn, name, unit, (data.get("name_zh") or "").strip() or None, _num(data.get("target_price"))
                )
                return self._json({"id": pid})
            if path == "/api/prices":
                pid, store, price = int(data["product_id"]), data.get("store"), _num(data.get("price"))
                qty = _num(data.get("qty")) or 1
                if store not in STORES or price is None or price <= 0 or qty <= 0 or not db.get_product(conn, pid):
                    return self._json({"error": "Pick a store and enter a valid price"}, 400)
                alerts = record_and_alert(
                    conn, pid, store, price, qty, note=data.get("note") or None, url=data.get("url") or None
                )
                return self._json({"alerts": alerts})
            if path.startswith("/api/products/") and path.endswith("/delete"):
                db.remove_product(conn, int(path.split("/")[3]))
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
