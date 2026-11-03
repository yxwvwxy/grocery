"""Build the read-only copy of the dashboard: one HTML file with today's data embedded.

The copy is written to docs/index.html, which GitHub Pages serves at
https://yxwvwxy.github.io/grocery/ so anyone with the link can open it. It is the same
page as the local dashboard, in read-only mode (see SNAPSHOT in static/index.html).
"""
import base64
import json
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
    # The data goes in before the page's own script, which reads it on load.
    return page.replace("</head>", "<script>window.PRICEWATCH_SNAPSHOT = " + data + ";</script>\n</head>", 1)
