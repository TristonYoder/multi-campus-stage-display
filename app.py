#!/usr/bin/env python3
"""
Multi-Campus Stage Display — macOS menu bar app.
Bundles the Flask server and serves it from the system tray.
"""
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

import json
import urllib.request

import rumps

PORT = 6767
REPO = "TristonYoder/multi-campus-stage-display"

# Resolve bundled resource path (works both in .app and plain Python)
def _resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / name)

def _current_version() -> str:
    try:
        return Path(_resource("VERSION")).read_text().strip()
    except Exception:
        return "0.0.0"

# ── Data directory ────────────────────────────────────────────────────────────
# Use ~/Library/Application Support/ so data survives app updates.
DATA_DIR = Path.home() / "Library" / "Application Support" / "Multi-Campus Stage Display"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["STAGE_DISPLAY_DATA_DIR"] = str(DATA_DIR)

# Seed campuses.json from the bundle on first launch
_bundle_dir = Path(__file__).parent
_bundle_campuses = _bundle_dir / "campuses.json"
if not (DATA_DIR / "campuses.json").exists() and _bundle_campuses.exists():
    shutil.copy(_bundle_campuses, DATA_DIR / "campuses.json")
if not (DATA_DIR / "data.json").exists():
    (DATA_DIR / "data.json").write_text("{}")

# Import server after env var is set
from server import app as flask_app, set_notify_hook  # noqa: E402


def _format_slot_list(slots: list[str]) -> str:
    """['Host-Mid', 'Host-Post'] → 'Host-Mid and Host-Post'"""
    if len(slots) == 1:
        return slots[0]
    return ", ".join(slots[:-1]) + f" and {slots[-1]}"


def _send_notification(changed: list[str], campus_name: str, ts: str):
    """Called from a Flask worker thread whenever content is saved."""
    rumps.notification(
        title=f"{campus_name} confidence update",
        subtitle=f"New {_format_slot_list(changed)} Content",
        message=ts,
        sound=False,
    )


# ── Menu bar app ──────────────────────────────────────────────────────────────
class StageDisplayApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Multi-Campus Stage Display",
            icon=_resource("icon.png"),
            template=False,
            quit_button=rumps.MenuItem("Quit Multi-Campus Stage Display"),
        )
        self.menu = [
            rumps.MenuItem("Multi-Campus Stage Display", callback=None),
            None,
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            rumps.MenuItem("Check for Updates…", callback=self._check_for_update),
            None,
        ]
        set_notify_hook(_send_notification)
        self._start_server()
        # Check for updates once at launch, then every 24 hours
        rumps.Timer(self._check_for_update, 86400).start()
        self._check_for_update(None)

    def _check_for_update(self, sender):
        manual = sender is not None  # False when called by the timer
        try:
            url = f"https://api.github.com/repos/{REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "MultiCampusStageDisplay"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
            latest = data.get("tag_name", "").lstrip("v")
            current = _current_version()
            if latest and latest != current:
                rumps.notification(
                    title="Update Available",
                    subtitle=f"Multi-Campus Stage Display {latest}",
                    message="Download the latest DMG from GitHub releases.",
                    sound=False,
                )
            elif manual:
                rumps.notification(
                    title="You're up to date",
                    subtitle=f"Multi-Campus Stage Display {current}",
                    message="No updates available.",
                    sound=False,
                )
        except Exception:
            if manual:
                rumps.notification(
                    title="Update check failed",
                    subtitle="Could not reach GitHub.",
                    message="Check your internet connection and try again.",
                    sound=False,
                )

    def _start_server(self):
        t = threading.Thread(
            target=lambda: flask_app.run(
                host="0.0.0.0", port=PORT, use_reloader=False, threaded=True
            ),
            daemon=True,
        )
        t.start()

    def open_browser(self, _):
        webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    StageDisplayApp().run()
