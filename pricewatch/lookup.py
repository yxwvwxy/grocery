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
    claude = find_claude()
    if not claude:
        return _finish(product_id, "failed", "Claude Code is not installed on this Mac.")
    conn = db.connect()
    product = db.get_product(conn, product_id)
    conn.close()
    prompt = (
        "Read pricewatch/LOOKUP.md and follow it for product #{id} ({name}) only. "
        "It was just added to the tracking list, so it has no prices yet."
    ).format(id=product_id, name=product["name"] + (" " + product["name_zh"] if product["name_zh"] else ""))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PRICEWATCH_QUIET="1")
    try:
        proc = subprocess.run(
            [claude, "-p", prompt, "--model", MODEL, "--output-format", "json",
             "--allowedTools", *ALLOWED_TOOLS],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30 * 60,
        )
    except subprocess.TimeoutExpired:
        return _finish(product_id, "failed", "The price lookup took more than 30 minutes and was stopped.")
    (LOG_DIR / "{}.log".format(product_id)).write_text(proc.stdout + proc.stderr)
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        result = {"is_error": True, "result": (proc.stderr or proc.stdout).strip()[-300:]}
    text = (result.get("result") or "").strip()
    if "Not logged in" in text:
        return _finish(product_id, "failed", "Claude Code isn't signed in on this Mac yet.")
    if proc.returncode or result.get("is_error"):
        return _finish(product_id, "failed", "The price lookup failed: " + (text[:200] or "no details"))
    _finish(product_id, "done", "Prices looked up.")
