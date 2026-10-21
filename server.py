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

# Seed a fresh data dir (e.g. an empty Docker volume) with the bundled default config
_bundled_campuses = Path(__file__).parent / "campuses.json"
if not CAMPUSES_FILE.exists() and _bundled_campuses.exists():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAMPUSES_FILE.write_text(_bundled_campuses.read_text())


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
    scheduled = active_scheduled_text(campus_id, key, data)
    if scheduled is not None:
        content = scheduled
    else:
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


# ── Schedule helpers ──────────────────────────────────────────────────────────

def active_scheduled_text(campus_id, slot_key, data):
    """Return the currently active scheduled text for a slot, or None if no entry has fired."""
    entries = data.get("schedules", {}).get(campus_id, {}).get(slot_key, [])
    if not entries:
        return None
    now = datetime.now().strftime("%H:%M")
    active = None
    for entry in sorted(entries, key=lambda e: e.get("time", "")):
        if entry.get("time", "") <= now:
            active = entry.get("text", "")
    return active


def _valid_campus(campus_id):
    return campus_id in {c["id"] for c in load_campuses()}


# ── Content API ───────────────────────────────────────────────────────────────

@app.route("/api/slots")
def api_slots():
    return jsonify(load_slots())

@app.route("/api/campuses")
def api_campuses():
    return jsonify(load_campuses())

@app.route("/api/campuses/<campus_id>")
def api_campus_get(campus_id):
    campus = next((c for c in load_campuses() if c["id"] == campus_id), None)
    if not campus:
        return jsonify({"error": "Not found"}), 404
    return jsonify(campus)

@app.route("/api/content/<campus_id>", methods=["GET"])
def api_get(campus_id):
    with _lock:
        data = load_data()
    slots = load_slots()
    result = {}
    for s in slots:
        key = slug_to_key(s["slug"])
        scheduled = active_scheduled_text(campus_id, key, data)
        if scheduled is not None:
            result[key] = scheduled
        else:
            result[key] = data.get(campus_id, {}).get(key, "")
    return jsonify(result)

@app.route("/api/content/<campus_id>/<slot_slug>", methods=["GET"])
def api_slot_get(campus_id, slot_slug):
    if not _valid_campus(campus_id) or not _valid_slug(slot_slug):
        return jsonify({"error": "Not found"}), 404
    key = slug_to_key(slot_slug)
    with _lock:
        data = load_data()
    scheduled = active_scheduled_text(campus_id, key, data)
    value = scheduled if scheduled is not None else data.get(campus_id, {}).get(key, "")
    return jsonify({"value": value})

@app.route("/api/content/<campus_id>/<slot_slug>", methods=["PUT"])
def api_slot_put(campus_id, slot_slug):
    if not _valid_campus(campus_id) or not _valid_slug(slot_slug):
        return jsonify({"error": "Not found"}), 404
    key = slug_to_key(slot_slug)
    text = request.get_data(as_text=True)
    with _lock:
        data = load_data()
        old_val = data.get(campus_id, {}).get(key, "")
        data.setdefault(campus_id, {})[key] = text
        save_data(data)
    if _notify_hook and text != old_val:
        slots = load_slots()
        campus_name = next((c["name"] for c in load_campuses() if c["id"] == campus_id), campus_id.title())
        label = next((s["label"] for s in slots if s["slug"] == slot_slug), slot_slug)
        ts = datetime.now().strftime("%Y.%m.%d %H:%M")
        _notify_hook([label], campus_name, ts)
    return jsonify({"ok": True})

@app.route("/api/content/<campus_id>/<slot_slug>", methods=["DELETE"])
def api_slot_delete(campus_id, slot_slug):
    if not _valid_campus(campus_id) or not _valid_slug(slot_slug):
        return jsonify({"error": "Not found"}), 404
    key = slug_to_key(slot_slug)
    with _lock:
        data = load_data()
        data.setdefault(campus_id, {})[key] = ""
        save_data(data)
    return jsonify({"ok": True})

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


# ── Schedule API ──────────────────────────────────────────────────────────────

@app.route("/api/schedule/<campus_id>/<slot_slug>", methods=["GET"])
def api_schedule_get(campus_id, slot_slug):
    if not _valid_campus(campus_id) or not _valid_slug(slot_slug):
        return jsonify({"error": "Not found"}), 404
    key = slug_to_key(slot_slug)
    with _lock:
        data = load_data()
    return jsonify(data.get("schedules", {}).get(campus_id, {}).get(key, []))

@app.route("/api/schedule/<campus_id>/<slot_slug>", methods=["PUT"])
def api_schedule_put(campus_id, slot_slug):
    if not _valid_campus(campus_id) or not _valid_slug(slot_slug):
        return jsonify({"error": "Not found"}), 404
    key = slug_to_key(slot_slug)
    entries = request.get_json(force=True)
    if not isinstance(entries, list):
        return jsonify({"error": "Expected JSON array"}), 400
    clean = []
    for e in entries:
        t = str(e.get("time", "")).strip()
        text = str(e.get("text", "")).strip()
        if t:
            clean.append({"time": t, "text": text})
    clean.sort(key=lambda e: e["time"])
    with _lock:
        data = load_data()
        data.setdefault("schedules", {}).setdefault(campus_id, {})[key] = clean
        save_data(data)
    # Immediately update the PP timer for this campus
    threading.Thread(target=_check_and_update_timer, args=(campus_id,), daemon=True).start()
    return jsonify({"ok": True})


# ── Config API ────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def api_config_post():
    body = request.get_json(force=True)

    # Validate + normalise slots; collect old→new slug renames
    slots = []
    renames = {}  # old_key → new_key
    for s in body.get("slots", []):
        label     = s.get("label",     "").strip()
        slug      = s.get("slug",      "").strip()
        old_slug  = s.get("old_slug",  "").strip()
        scheduled = bool(s.get("scheduled", False))
        if label and slug:
            slots.append({"label": label, "slug": slug, "scheduled": scheduled})
            old_key = slug_to_key(old_slug) if old_slug else None
            new_key = slug_to_key(slug)
            if old_key and old_key != new_key:
                renames[old_key] = new_key

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
        # Preserve per-campus slot_timers that are managed outside Settings
        existing = {c["id"]: c for c in load_config().get("campuses", [])}
        for campus in campuses:
            if campus["id"] in existing:
                campus["slot_timers"] = existing[campus["id"]].get("slot_timers", {})
        save_config({"slots": slots, "campuses": campuses})
        if renames:
            data = load_data()
            # Migrate per-campus content keys
            for campus in campuses:
                cdata = data.get(campus["id"], {})
                for old_key, new_key in renames.items():
                    if old_key in cdata:
                        cdata[new_key] = cdata.pop(old_key)
                if cdata:
                    data[campus["id"]] = cdata
            # Migrate per-campus schedule keys
            schedules = data.get("schedules", {})
            for campus_sched in schedules.values():
                for old_key, new_key in renames.items():
                    if old_key in campus_sched:
                        campus_sched[new_key] = campus_sched.pop(old_key)
            if schedules:
                data["schedules"] = schedules
            save_data(data)

    return jsonify({"ok": True})


# ── Import / export ───────────────────────────────────────────────────────────

EXPORT_FORMAT = "multi-campus-stage-display"
EXPORT_VERSION = 1


@app.route("/api/export", methods=["GET"])
def api_export():
    """Download campus configuration plus current notes/schedules as one JSON file."""
    with _lock:
        cfg = load_config()
        data = load_data()
    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": cfg,
        "data": data,
    }
    filename = f"stage-display-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return app.response_class(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _normalize_import_config(cfg):
    """Validate an imported config; return (clean_config, error)."""
    if not isinstance(cfg, dict):
        return None, "config must be an object"
    raw_slots, raw_campuses = cfg.get("slots", []), cfg.get("campuses", [])
    if not isinstance(raw_slots, list) or not isinstance(raw_campuses, list):
        return None, "config.slots and config.campuses must be arrays"

    slots, seen_slugs = [], set()
    for s in raw_slots:
        if not isinstance(s, dict):
            return None, "each slot must be an object"
        label = str(s.get("label", "")).strip()
        slug = str(s.get("slug", "")).strip()
        if not label or not slug:
            return None, "each slot needs a label and slug"
        if slug in seen_slugs:
            return None, f"duplicate slot slug: {slug}"
        seen_slugs.add(slug)
        slots.append({"label": label, "slug": slug, "scheduled": bool(s.get("scheduled", False))})

    campuses, seen_ids = [], set()
    for c in raw_campuses:
        if not isinstance(c, dict):
            return None, "each campus must be an object"
        cid = str(c.get("id", "")).strip()
        name = str(c.get("name", "")).strip()
        if not cid or not name:
            return None, "each campus needs an id and name"
        if cid in seen_ids:
            return None, f"duplicate campus id: {cid}"
        seen_ids.add(cid)
        nets = c.get("networks", [])
        if not isinstance(nets, list):
            return None, f"campus {cid}: networks must be an array"
        try:
            pp_port = int(c.get("propresenter_port") or 53072)
        except (TypeError, ValueError):
            return None, f"campus {cid}: propresenter_port must be a number"
        slot_timers = c.get("slot_timers", {})
        if not isinstance(slot_timers, dict):
            return None, f"campus {cid}: slot_timers must be an object"
        campuses.append({
            "id": cid,
            "name": name,
            "networks": [str(n).strip() for n in nets if str(n).strip()],
            "propresenter_host": str(c.get("propresenter_host") or "").strip(),
            "propresenter_port": pp_port,
            "slot_timers": {str(k): str(v) for k, v in slot_timers.items()},
        })

    return {"slots": slots, "campuses": campuses}, None


def _validate_import_data(data):
    """Validate imported notes/schedules; return error string or None."""
    if not isinstance(data, dict):
        return "data must be an object"
    for key, value in data.items():
        if not isinstance(value, dict):
            return f"data.{key} must be an object"
        if key == "schedules":
            for cid, slots in value.items():
                if not isinstance(slots, dict):
                    return f"data.schedules.{cid} must be an object"
                for slot_key, entries in slots.items():
                    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
                        return f"data.schedules.{cid}.{slot_key} must be an array of objects"
    return None


@app.route("/api/import", methods=["POST"])
def api_import():
    """Restore an export file. Replaces config and/or notes, whichever the file contains."""
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "File is not valid JSON"}), 400

    # Also accept a bare campuses.json (top-level slots/campuses)
    if "config" not in body and "data" not in body and ("slots" in body or "campuses" in body):
        body = {"config": body}
    if body.get("format", EXPORT_FORMAT) != EXPORT_FORMAT:
        return jsonify({"error": "Not a stage display export file"}), 400
    if "config" not in body and "data" not in body:
        return jsonify({"error": "File contains no config or data"}), 400

    cfg = data = None
    if "config" in body:
        cfg, err = _normalize_import_config(body["config"])
        if err:
            return jsonify({"error": f"Invalid config: {err}"}), 400
    if "data" in body:
        data = body["data"]
        err = _validate_import_data(data)
        if err:
            return jsonify({"error": f"Invalid data: {err}"}), 400

    with _lock:
        if cfg is not None:
            save_config(cfg)
        if data is not None:
            save_data(data)

    for campus in load_campuses():
        threading.Thread(target=_check_and_update_timer, args=(campus["id"],), daemon=True).start()

    return jsonify({
        "ok": True,
        "imported_config": cfg is not None,
        "imported_data": data is not None,
    })


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




@app.route("/api/campus/<campus_id>/slot-timers", methods=["PUT"])
def campus_slot_timers_put(campus_id):
    body = request.get_json(force=True) or {}
    slot_timers = body.get("slot_timers", {})
    if not isinstance(slot_timers, dict):
        return jsonify({"error": "slot_timers must be an object"}), 400
    with _lock:
        cfg = load_config()
        for campus in cfg.get("campuses", []):
            if campus["id"] == campus_id:
                campus["slot_timers"] = slot_timers
                break
        else:
            return jsonify({"error": "campus not found"}), 404
        save_config(cfg)
    _check_and_update_timer(campus_id)
    return jsonify({"ok": True})


@app.route("/api/campus/<campus_id>/pp-timers", methods=["GET"])
def pp_timers_list(campus_id):
    host, port = _pp_base(campus_id)
    if not host:
        return jsonify([])
    timers, status = _pp_json_request("GET", f"http://{host}:{port}/v1/timers")
    if timers is None:
        return jsonify([])
    return jsonify([{"name": t["id"]["name"], "uuid": t["id"]["uuid"]} for t in timers])


@app.route("/api/campus/<campus_id>/pp-status", methods=["GET"])
def pp_status(campus_id):
    """Report whether this campus's ProPresenter API is reachable."""
    if not _valid_campus(campus_id):
        return jsonify({"error": "Not found"}), 404
    host, port = _pp_base(campus_id)
    if not host:
        return jsonify({"configured": False, "connected": False})
    info, status = _pp_json_request("GET", f"http://{host}:{port}/version")
    connected = status == 200
    result = {"configured": True, "connected": connected, "host": host, "port": port}
    if connected and isinstance(info, dict) and info.get("name"):
        result["name"] = info["name"]
    return jsonify(result)


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


# ── ProPresenter auto-timer ───────────────────────────────────────────────────

def _pp_json_request(method, url, body=None):
    req = urllib.request.Request(url, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode() or "null"), r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, 502


def _set_pp_countdown_to_time(host, port, timer_id, target_hhmm):
    """Start a named PP timer counting down to the given HH:MM time of day.
    Uses PUT /v1/timer/{id}/start with count_down_to_time."""
    h, m = map(int, target_hhmm.split(":"))
    time_of_day = h * 3600 + m * 60
    period = "am" if h < 12 else "pm"
    body = {
        "id": {"name": str(timer_id)},
        "allows_overrun": False,
        "count_down_to_time": {"time_of_day": time_of_day, "period": period},
    }
    import urllib.parse
    encoded_id = urllib.parse.quote(str(timer_id), safe="")
    url = f"http://{host}:{port}/v1/timer/{encoded_id}/start"
    _, status = _pp_json_request("PUT", url, body)
    if status not in (200, 204):
        print(f"[timer] PUT /v1/timer/{timer_id}/start returned {status}")
        return False
    print(f"[timer] started '{timer_id}' counting down to {target_hhmm}")
    return True


def _next_transition_time(campus_id, data):
    """Return the HH:MM of the next scheduled transition for this campus, or None."""
    scheduled_keys = {slug_to_key(s["slug"]) for s in load_slots() if s.get("scheduled")}
    if not scheduled_keys:
        return None
    now_hhmm = datetime.now().strftime("%H:%M")
    earliest = None
    for key in scheduled_keys:
        entries = data.get("schedules", {}).get(campus_id, {}).get(key, [])
        for e in entries:
            t = e.get("time", "")
            if t > now_hhmm:
                if earliest is None or t < earliest:
                    earliest = t
    return earliest


def _check_and_update_timer(campus_id):
    """For each scheduled slot with a configured timer, set its PP timer to the next transition."""
    campus = next((c for c in load_campuses() if c["id"] == campus_id), None)
    if not campus:
        return
    host = campus.get("propresenter_host", "").strip()
    port = int(campus.get("propresenter_port") or 53072)
    if not host:
        return
    slot_timers = campus.get("slot_timers", {})
    if not slot_timers:
        return
    with _lock:
        data = load_data()
    now_hhmm = datetime.now().strftime("%H:%M")
    scheduled_slots = [s for s in load_slots() if s.get("scheduled")]
    for slot in scheduled_slots:
        slug = slot["slug"]
        timer_id = slot_timers.get(slug, "").strip()
        if not timer_id:
            continue
        slot_key = slug_to_key(slug)
        entries = data.get("schedules", {}).get(campus_id, {}).get(slot_key, [])
        next_time = None
        for e in sorted(entries, key=lambda x: x.get("time", "")):
            if e.get("time", "") > now_hhmm:
                next_time = e["time"]
                break
        if next_time:
            _set_pp_countdown_to_time(host, port, timer_id, next_time)


def _scheduler_loop():
    """Background thread — wakes at each minute boundary to update PP timers."""
    import time
    while True:
        # Sleep until the next whole minute
        now = datetime.now()
        sleep_secs = 60 - now.second - now.microsecond / 1_000_000
        time.sleep(max(sleep_secs, 1))
        try:
            for campus in load_campuses():
                _check_and_update_timer(campus["id"])
        except Exception as e:
            print(f"[timer] scheduler error: {e}")


# Start background timer thread (guard against Flask debug-mode double-start)
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    threading.Thread(target=_scheduler_loop, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 6767))
    app.run(host="0.0.0.0", port=port)
