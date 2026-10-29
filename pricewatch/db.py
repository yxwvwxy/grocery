"""SQLite storage: a product is sold at several stores (listings), each with its own price history.

Prices are recorded per pack together with the pack quantity, so stores selling
different pack sizes are compared by unit price (price / qty).
"""
import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("PRICEWATCH_DB") or Path(__file__).resolve().parent.parent / "data" / "prices.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,         -- English name
    name_zh      TEXT,                  -- Chinese name
    unit         TEXT NOT NULL,         -- what one unit is: 'lb', 'egg', 'oz', 'pack' ...
    target_price REAL,                  -- alert when a store's unit price is at or below this
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store      TEXT NOT NULL,
    url        TEXT,                    -- product page, for automatic price checks
    image_url  TEXT,                    -- product photo, as shown on the store's own site
    qty        REAL NOT NULL DEFAULT 1, -- units per pack at this store, used by auto checks
    UNIQUE (product_id, store)
);
CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY,
    listing_id  INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    price       REAL NOT NULL,          -- pack price
    qty         REAL NOT NULL DEFAULT 1,
    source      TEXT NOT NULL,          -- 'auto' (fetched) or 'manual'
    note        TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_listing ON prices(listing_id, recorded_at);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    if "image_url" not in cols:
        conn.execute("ALTER TABLE listings ADD COLUMN image_url TEXT")
        conn.commit()
    return conn


def add_product(conn, name, unit, name_zh=None, target_price=None):
    cur = conn.execute(
        "INSERT INTO products (name, name_zh, unit, target_price, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, name_zh, unit, target_price, now()),
    )
    conn.commit()
    return cur.lastrowid


def remove_product(conn, product_id):
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()


def get_product(conn, product_id):
    return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def set_listing_image(conn, product_id, store, image_url):
    """Attach a product photo (as shown on the store's own site) to a listing."""
    conn.execute(
        "INSERT OR IGNORE INTO listings (product_id, store) VALUES (?, ?)", (product_id, store)
    )
    conn.execute(
        "UPDATE listings SET image_url = ? WHERE product_id = ? AND store = ?", (image_url, product_id, store)
    )
    conn.commit()


def get_or_create_listing(conn, product_id, store, url=None, qty=None):
    """Return the listing id for (product, store), creating it and updating url/qty when given."""
    conn.execute(
        "INSERT OR IGNORE INTO listings (product_id, store) VALUES (?, ?)", (product_id, store)
    )
    if url:
        conn.execute("UPDATE listings SET url = ? WHERE product_id = ? AND store = ?", (url, product_id, store))
    if qty:
        conn.execute("UPDATE listings SET qty = ? WHERE product_id = ? AND store = ?", (qty, product_id, store))
    conn.commit()
    return conn.execute(
        "SELECT id FROM listings WHERE product_id = ? AND store = ?", (product_id, store)
    ).fetchone()["id"]


def record_price(conn, listing_id, price, qty=1, source="manual", note=None):
    conn.execute(
        "INSERT INTO prices (listing_id, price, qty, source, note, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (listing_id, price, qty, source, note, now()),
    )
    conn.commit()


def listings_with_url(conn):
    rows = conn.execute(
        """SELECT l.*, p.name, p.name_zh FROM listings l JOIN products p ON p.id = l.product_id
           WHERE l.url IS NOT NULL ORDER BY p.name COLLATE NOCASE, l.store"""
    ).fetchall()
    return [dict(r) for r in rows]


def overview(conn):
    """Every product with its stores, each store's latest/previous/lowest unit price.

    A product's listings are sorted cheapest first by latest unit price;
    stores with no price yet go last.
    """
    products = [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE")]
    history_by_listing = defaultdict(list)
    for r in conn.execute("SELECT * FROM prices ORDER BY recorded_at, id"):
        history_by_listing[r["listing_id"]].append(r)
    listings_by_product = defaultdict(list)
    for l in conn.execute("SELECT * FROM listings"):
        hist = history_by_listing[l["id"]]
        units = [h["price"] / h["qty"] for h in hist]
        listings_by_product[l["product_id"]].append({
            "id": l["id"],
            "store": l["store"],
            "url": l["url"],
            "image_url": l["image_url"],
            "price": hist[-1]["price"] if hist else None,
            "qty": hist[-1]["qty"] if hist else l["qty"],
            "unit_price": units[-1] if units else None,
            "previous_unit_price": units[-2] if len(units) > 1 else None,
            "lowest_unit_price": min(units) if units else None,
            "recorded_at": hist[-1]["recorded_at"] if hist else None,
            "note": hist[-1]["note"] if hist else None,
        })
    for p in products:
        ls = listings_by_product[p["id"]]
        ls.sort(key=lambda l: (l["unit_price"] is None, l["unit_price"] or 0))
        p["listings"] = ls
        p["best_store"] = ls[0]["store"] if ls and ls[0]["unit_price"] is not None else None
    return products


def history(conn, product_id):
    rows = conn.execute(
        """SELECT l.store, pr.price, pr.qty, pr.price / pr.qty AS unit_price, pr.source, pr.note, pr.recorded_at
           FROM prices pr JOIN listings l ON l.id = pr.listing_id
           WHERE l.product_id = ? ORDER BY pr.recorded_at, pr.id""",
        (product_id,),
    ).fetchall()
    return [dict(r) for r in rows]
