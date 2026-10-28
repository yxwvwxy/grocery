import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("PRICEWATCH_DB") or Path(__file__).resolve().parent.parent / "data" / "prices.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    store        TEXT NOT NULL,
    url          TEXT,
    unit         TEXT,
    target_price REAL,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price       REAL NOT NULL,
    source      TEXT NOT NULL,          -- 'auto' (fetched) or 'manual'
    note        TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_item ON prices(item_id, recorded_at);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


def connect(path=DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def add_item(conn, name, store, url=None, unit=None, target_price=None):
    cur = conn.execute(
        "INSERT INTO items (name, store, url, unit, target_price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, store, url, unit, target_price, now()),
    )
    conn.commit()
    return cur.lastrowid


def remove_item(conn, item_id):
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()


def record_price(conn, item_id, price, source="manual", note=None):
    conn.execute(
        "INSERT INTO prices (item_id, price, source, note, recorded_at) VALUES (?, ?, ?, ?, ?)",
        (item_id, price, source, note, now()),
    )
    conn.commit()


def get_item(conn, item_id):
    return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def list_items(conn):
    """Items with their latest, previous, lowest and highest recorded prices."""
    rows = conn.execute(
        """
        SELECT i.*,
               (SELECT price FROM prices WHERE item_id = i.id ORDER BY recorded_at DESC, id DESC LIMIT 1) AS latest,
               (SELECT price FROM prices WHERE item_id = i.id ORDER BY recorded_at DESC, id DESC LIMIT 1 OFFSET 1) AS previous,
               (SELECT recorded_at FROM prices WHERE item_id = i.id ORDER BY recorded_at DESC, id DESC LIMIT 1) AS latest_at,
               (SELECT MIN(price) FROM prices WHERE item_id = i.id) AS lowest,
               (SELECT MAX(price) FROM prices WHERE item_id = i.id) AS highest
        FROM items i
        ORDER BY i.name COLLATE NOCASE, i.store
        """
    ).fetchall()
    return [dict(r) for r in rows]


def history(conn, item_id):
    rows = conn.execute(
        "SELECT price, source, note, recorded_at FROM prices WHERE item_id = ? ORDER BY recorded_at, id",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]
