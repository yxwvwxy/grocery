"""Run Claude Code in the background to look up one product's prices (see LOOKUP.md).

The dashboard starts a lookup when a product is tracked; the job runs `claude -p` in the
repository, which records prices through the `python3 -m pricewatch` command line.
"""
import glob
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "lookups"
MODEL = "claude-sonnet-5-5"
ALLOWED_TOOLS = ["Read", "WebSearch", "WebFetch", "Bash(python3 -m pricewatch:*)"]

_jobs = {}  # product_id -> {"state": "running" | "done" | "failed", "message": str, "started": float}
_lock = threading.Lock()


def find_claude():
    """The `claude` command: one on PATH, the standard install, or the copy bundled with the desktop app."""
    found = shutil.which("claude")
    if found:
        return found
    for path in (Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude"):
        if path.is_file():
            return str(path)
    bundled = glob.glob(str(
        Path.home() / "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"))
    # Newest app version first (directory names are versions like 2.1.309).
    bundled.sort(key=lambda p: [int(x) if x.isdigit() else 0 for x in Path(p).parts[-6].split(".")], reverse=True)
    return bundled[0] if bundled else None


def status(product_id):
    with _lock:
        job = _jobs.get(product_id)
        return dict(job) if job else None


def start(product_id):
    """Start a background lookup for one product unless one is already running."""
    with _lock:
        job = _jobs.get(product_id)
        if job and job["state"] == "running":
            return
        _jobs[product_id] = {"state": "running", "message": "Looking up prices…", "started": time.time()}
    threading.Thread(target=_run, args=(product_id,), daemon=True).start()


def _finish(product_id, state, message):
    with _lock:
        _jobs[product_id].update(state=state, message=message)


def _run(product_id):
    _finish(product_id, *lookup_once(product_id))


def lookup_once(product_id):
    """Look up one product's prices now and wait for it; returns (state, message).

    Used by the dashboard (in a background thread) and by `pricewatch refresh`, which
    runs the weekly refresh one product at a time. Tools are allowed up front, so a
    lookup never stops to ask for permission.
    """
    claude = find_claude()
    if not claude:
        return "failed", "Claude Code is not installed on this Mac."
    conn = db.connect()
    product = db.get_product(conn, product_id)
    has_prices = conn.execute(
        "SELECT 1 FROM prices pr JOIN listings l ON l.id = pr.listing_id WHERE l.product_id = ? LIMIT 1",
        (product_id,),
    ).fetchone()
    conn.close()
    name = product["name"] + (" " + product["name_zh"] if product["name_zh"] else "")
    prompt = "Read pricewatch/LOOKUP.md and follow it for product #{} ({}) only. ".format(product_id, name) + (
        "It already has prices: re-price every existing item with its exact --variant text so its history "
        "continues, and add the items and stores the rules call for that are still missing."
        if has_prices else "It was just added to the tracking list, so it has no prices yet.")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PRICEWATCH_QUIET="1")
    try:
        proc = subprocess.run(
            [claude, "-p", prompt, "--model", MODEL, "--output-format", "json",
             "--allowedTools", *ALLOWED_TOOLS],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30 * 60,
        )
    except subprocess.TimeoutExpired:
        return "failed", "The price lookup took more than 30 minutes and was stopped."
    (LOG_DIR / "{}.log".format(product_id)).write_text(proc.stdout + proc.stderr)
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        result = {"is_error": True, "result": (proc.stderr or proc.stdout).strip()[-300:]}
    text = (result.get("result") or "").strip()
    if "Not logged in" in text:
        return "failed", "Claude Code isn't signed in on this Mac yet."
    if proc.returncode or result.get("is_error"):
        return "failed", "The price lookup failed: " + (text[:200] or "no details")
    return "done", "Prices looked up."
