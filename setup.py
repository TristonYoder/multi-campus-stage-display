"""py2app build configuration for Campus Stage Displays."""
from setuptools import setup

APP = ["app.py"]
DATA_FILES = [
    ("", ["campuses.json"]),
    ("templates", ["templates/index.html"]),
]
OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "flask",
        "jinja2",
        "werkzeug",
        "click",
        "itsdangerous",
        "markupsafe",
        "rumps",
    ],
    "includes": ["server"],
    "plist": {
        "CFBundleName": "Campus Stage Displays",
        "CFBundleDisplayName": "Campus Stage Displays",
        "CFBundleIdentifier": "studio.7andco.stage-display",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHumanReadableCopyright": "7 and Co. Studio",
        # Menu bar only — no Dock icon
        "LSUIElement": True,
        "LSBackgroundOnly": False,
    },
}

setup(
    name="Campus Stage Displays",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
)
