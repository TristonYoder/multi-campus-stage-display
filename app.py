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

import rumps

PORT = 7474

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
from server import app as flask_app  # noqa: E402


# ── Menu bar app ──────────────────────────────────────────────────────────────
class StageDisplayApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Multi-Campus Stage Display",
            title="⬛",
            quit_button=rumps.MenuItem("Quit Multi-Campus Stage Display"),
        )
        self.menu = [
            rumps.MenuItem("Multi-Campus Stage Display", callback=None),
            None,
            rumps.MenuItem("Open in Browser", callback=self.open_browser),
            None,
        ]
        self._start_server()

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
