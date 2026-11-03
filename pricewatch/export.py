"""Build the read-only copy of the dashboard: one HTML file with today's data embedded.

The copy is published as a claude.ai artifact so others can open it. It is the same
page as the local dashboard, in read-only mode (see SNAPSHOT in static/index.html).
"""
import base64
import json
import re
from datetime import datetime

from . import STORES, db
from .server import STATIC


def build(conn):
    products = db.overview(conn)
    history = {p["id"]: db.history(conn, p["id"]) for p in products}
    icons = {}
    for k in STORES:
        icon = STATIC / "icons" / (k + ".png")
        if icon.is_file():
            icons[k] = "data:image/png;base64," + base64.b64encode(icon.read_bytes()).decode()
    stamps = [l["recorded_at"] for p in products for l in p["listings"] if l.get("recorded_at")]
    as_of = max(stamps)[:10] if stamps else datetime.now().strftime("%Y-%m-%d")
    snapshot = {"stores": STORES, "products": products, "history": history, "icons": icons,
                "as_of": "{}/{}/{}".format(int(as_of[5:7]), int(as_of[8:10]), as_of[:4])}
    data = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")

    page = (STATIC / "index.html").read_text("utf-8")
    head = re.search(r"<head>(.*?)</head>", page, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", page, re.S).group(1)
    # The artifact viewer supplies the doctype, charset and viewport; keep the title, Chart.js and styles.
    head = re.sub(r'<meta[^>]*>\s*', "", head)
    return head.strip() + "\n<script>window.PRICEWATCH_SNAPSHOT = " + data + ";</script>\n" + body.strip() + "\n"
