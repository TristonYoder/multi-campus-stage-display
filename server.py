#!/usr/bin/env python3
import ipaddress
import json
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Notification hook — set by app.py when running as the macOS menu bar app.
# Signature: notify_hook(campus_name: str, slot_label: str)
_notify_hook = None

def set_notify_hook(fn):
    global _notify_hook
    _notify_hook = fn

# When bundled as a .app, data lives in ~/Library/Application Support/
# so it persists across app updates. Override with STAGE_DISPLAY_DATA_DIR.
_default_data_dir = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("STAGE_DISPLAY_DATA_DIR", _default_data_dir))
CAMPUSES_FILE = DATA_DIR / "campuses.json"
DATA_FILE     = DATA_DIR / "data.json"

_lock = threading.Lock()


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config():
    return json.loads(CAMPUSES_FILE.read_text())

def save_config(cfg):
    CAMPUSES_FILE.write_text(json.dumps(cfg, indent=2))

def load_campuses():
    return load_config().get("campuses", [])

def load_slots():
    return load_config().get("slots", [])

def slug_to_key(slug):
    return slug.replace("-", "_")


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_data():
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 2:
        return json.loads(DATA_FILE.read_text())
    return {}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))


# ── IP routing ────────────────────────────────────────────────────────────────

def campus_for_ip(ip_str):
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    for campus in load_campuses():
        for net in campus.get("networks", []):
            try:
                if addr in ipaddress.ip_network(net, strict=False):
                    return campus["id"]
            except ValueError:
                pass
    return None


# ── RSS builder ───────────────────────────────────────────────────────────────

def make_rss(campus_id, slot_slug, base_url):
    key = slug_to_key(slot_slug)
    with _lock:
        data = load_data()
    content = data.get(campus_id, {}).get(key, "")
    slots = load_slots()
    label = next((s["label"] for s in slots if s["slug"] == slot_slug), slot_slug)
    campus_name = next(
        (c["name"] for c in load_campuses() if c["id"] == campus_id),
        campus_id.title(),
    )
    title = f"{campus_name} – {label}"
    pub = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    item_title = escape(content) if content else "(empty)"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(title)}</title>
    <link>{base_url}</link>
    <description>{escape(title)} stage display content</description>
    <lastBuildDate>{pub}</lastBuildDate>
    <item>
      <title>{item_title}</title>
      <description>{escape(content)}</description>
      <pubDate>{pub}</pubDate>
      <guid isPermaLink="false">{campus_id}-{slot_slug}-{pub}</guid>
    </item>
  </channel>
</rss>"""


# ── UI ────────────────────────────────────────────────────────────────────────

def _render_index(initial_tab=None):
    cfg = load_config()
    campuses = cfg.get("campuses", [])
    if initial_tab is None:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        initial_tab = campus_for_ip(ip)  # None = no match → landing state
    return render_template("index.html",
                           campuses=campuses,
                           slots=cfg.get("slots", []),
                           initial_tab=initial_tab)

@app.route("/")
def index():
    return _render_index()

@app.route("/<slug>")
def campus_route(slug):
    # Only serve the UI for known campus IDs / special tabs; let other routes 404 naturally
    known = {c["id"] for c in load_campuses()} | {"__rss", "__config", "rss", "settings"}
    if slug in known:
        return _render_index(initial_tab=slug)
    return "Not found", 404


# ── Content API ───────────────────────────────────────────────────────────────

@app.route("/api/campuses")
def api_campuses():
    return jsonify(load_campuses())

@app.route("/api/content/<campus_id>", methods=["GET"])
def api_get(campus_id):
    with _lock:
        data = load_data()
    slots = load_slots()
    empty = {slug_to_key(s["slug"]): "" for s in slots}
    return jsonify({**empty, **data.get(campus_id, {})})

@app.route("/api/content/<campus_id>", methods=["POST"])
def api_post(campus_id):
    body = request.get_json(force=True)
    with _lock:
        data = load_data()
        old_campus = dict(data.get(campus_id, {}))
        data.setdefault(campus_id, {}).update(body)
        save_data(data)

    if _notify_hook:
        slots = load_slots()
        campus_name = next(
            (c["name"] for c in load_campuses() if c["id"] == campus_id),
            campus_id.title(),
        )
        ts = datetime.now().strftime("%Y.%m.%d %H:%M")
        # Only notify for slots whose value actually changed
        # old_campus captured before save (inside the lock above)
        changed = [
            slot["label"] for slot in slots
            if slug_to_key(slot["slug"]) in body
            and body[slug_to_key(slot["slug"])] != old_campus.get(slug_to_key(slot["slug"]), "")
        ]
        if changed:
            _notify_hook(changed, campus_name, ts)

    return jsonify({"ok": True})


# ── Config API ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def api_config_post():
    body = request.get_json(force=True)

    # Validate + normalise slots
    slots = []
    for s in body.get("slots", []):
        label = s.get("label", "").strip()
        slug  = s.get("slug",  "").strip()
        if label and slug:
            slots.append({"label": label, "slug": slug})

    # Validate + normalise campuses
    campuses = []
    for c in body.get("campuses", []):
        name = c.get("name", "").strip()
        cid  = c.get("id",   "").strip()
        nets = [n.strip() for n in c.get("networks", []) if n.strip()]
        pp_host = c.get("propresenter_host", "").strip()
        pp_port = int(c.get("propresenter_port") or 53072)
        if name and cid:
            entry = {"id": cid, "name": name, "networks": nets,
                     "propresenter_host": pp_host, "propresenter_port": pp_port}
            campuses.append(entry)

    with _lock:
        save_config({"slots": slots, "campuses": campuses})

    return jsonify({"ok": True})


# ── RSS ───────────────────────────────────────────────────────────────────────

def _valid_slug(slug):
    return slug in {s["slug"] for s in load_slots()}

def _rss_response(campus_id, slot_slug):
    valid_campuses = {c["id"] for c in load_campuses()}
    if campus_id not in valid_campuses or not _valid_slug(slot_slug):
        return "Not found", 404
    xml = make_rss(campus_id, slot_slug, request.url)
    return app.response_class(xml, mimetype="application/rss+xml")

@app.route("/rss/dynamic/<slot_slug>")
def rss_dynamic(slot_slug):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    campus_id = campus_for_ip(ip)
    if not campus_id:
        campuses = load_campuses()
        campus_id = campuses[0]["id"] if campuses else None
    if not campus_id:
        return "No campus configured", 404
    return _rss_response(campus_id, slot_slug)

@app.route("/rss/<campus_id>/<slot_slug>")
def rss_static(campus_id, slot_slug):
    return _rss_response(campus_id, slot_slug)


# ── ProPresenter stage message proxy ─────────────────────────────────────────

def _pp_base(campus_id):
    """Return (host, port) for the campus, or raise 404 if not configured."""
    campus = next((c for c in load_campuses() if c["id"] == campus_id), None)
    if not campus:
        return None, None
    host = campus.get("propresenter_host", "").strip()
    port = int(campus.get("propresenter_port") or 53072)
    return host, port

def _pp_request(method, url, body=None):
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.data = body.encode() if isinstance(body, str) else body
        req.add_header("Content-Type", "text/plain")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        return e.read().decode(), e.code
    except Exception as e:
        return str(e), 502




@app.route("/api/campus/<campus_id>/stage-message", methods=["GET"])
def pp_stage_message_get(campus_id):
    host, port = _pp_base(campus_id)
    if not host:
        return jsonify({"error": "ProPresenter not configured for this campus"}), 404
    body, status = _pp_request("GET", f"http://{host}:{port}/v1/stage/message")
    return body, status, {"Content-Type": "text/plain"}

@app.route("/api/campus/<campus_id>/stage-message", methods=["PUT"])
def pp_stage_message_set(campus_id):
    host, port = _pp_base(campus_id)
    if not host:
        return jsonify({"error": "ProPresenter not configured for this campus"}), 404
    message = request.get_data(as_text=True)
    # ProPresenter expects application/json with a JSON-encoded string body
    encoded = json.dumps(message)
    req = urllib.request.Request(f"http://{host}:{port}/v1/stage/message", method="PUT")
    req.data = encoded.encode()
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            body, status = r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode(), e.code
    except Exception as e:
        body, status = str(e), 502
    return body, status, {"Content-Type": "text/plain"}

@app.route("/api/campus/<campus_id>/stage-message", methods=["DELETE"])
def pp_stage_message_clear(campus_id):
    host, port = _pp_base(campus_id)
    if not host:
        return jsonify({"error": "ProPresenter not configured for this campus"}), 404
    body, status = _pp_request("DELETE", f"http://{host}:{port}/v1/stage/message")
    return body, status, {"Content-Type": "text/plain"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 6767))
    app.run(host="0.0.0.0", port=port)
