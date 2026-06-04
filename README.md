# Multi-Campus Stage Display

[![Build & Push](https://github.com/TristonYoder/multi-campus-stage-display/actions/workflows/docker.yml/badge.svg)](https://github.com/TristonYoder/multi-campus-stage-display/actions/workflows/docker.yml)

A web app for managing ProPresenter stage display content across multiple campuses. Each campus has editable display slots served as RSS feeds, consumed directly by ProPresenter's stage display.

## Features

- **Multi-campus tabs:** Automatically selects your campus tab based on your IP address
- **RSS feeds:** Per campus and slot, plus a dynamic feed that routes by requesting IP for unified ProPresenter configs
- **ProPresenter Config tab:** Copy RSS URLs ready to paste into ProPresenter
- **Settings tab:** Add/remove campuses and display types without touching config files
- **Direct URLs:** `/campus-name` opens straight to that campus tab
- **macOS menu bar app:** Runs in the background, sends notifications when content is updated
- **Auto-updates:** App checks daily for new releases and notifies you

---

## Deployment

### macOS App

The recommended way to run Multi-Campus Stage Display on a Mac.

**Install:**

1. Download `MultiCampusStageDisplay.dmg` from the [latest release](https://github.com/TristonYoder/multi-campus-stage-display/releases/latest)
2. Open the DMG, drag the app to Applications
3. Launch from Applications

The app runs as a **menu bar icon** with no Dock icon. Click the icon to access:
- **Open in Browser:** Opens the editor UI at `http://localhost:6767`
- **Check for Updates:** Manually checks for a new release
- **Quit**

Data is stored in `~/Library/Application Support/Multi-Campus Stage Display/` and persists across updates.

**Build locally:**

```bash
pip install -r requirements-mac.txt
pyinstaller app.py --name "Multi-Campus Stage Display" --windowed --noconfirm \
  --add-data "templates/index.html:templates" \
  --add-data "campuses.json:." \
  --add-data "icon.png:." \
  --add-data "VERSION:."
open "dist/Multi-Campus Stage Display.app"
```

---

### Docker

**Quick start (local):**

```bash
docker compose up -d
# open http://localhost:6767
```

**Server deployment:**

1. Create a directory and seed the data files:

```bash
mkdir -p /opt/stage-display && cd /opt/stage-display
echo '{}' > data.json
curl -o campuses.json \
  https://raw.githubusercontent.com/TristonYoder/multi-campus-stage-display/main/campuses.json
```

2. Create `docker-compose.yml`:

```yaml
services:
  stage-display:
    image: ghcr.io/tristonyoder/multi-campus-stage-display:latest
    ports:
      - "6767:6767"
    volumes:
      - ./campuses.json:/app/campuses.json
      - ./data.json:/app/data.json
    restart: always
```

3. Pull and start:

```bash
docker compose pull && docker compose up -d
```

**Updating:**

```bash
cd /opt/stage-display
docker compose pull && docker compose up -d
```

**Automatic updates with Watchtower:**

Add to `docker-compose.yml` to poll for new images every 5 minutes:

```yaml
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 stage-display-stage-display-1
```

**Making the package public (one-time, if using GHCR privately):**

1. Go to [github.com/TristonYoder](https://github.com/TristonYoder) > **Packages** > `multi-campus-stage-display`
2. **Package settings** > Change visibility > **Public**

Or keep it private and run `docker login ghcr.io` on each server before pulling.

**Reverse proxy (optional):**

Caddy:
```
stagedisplay.yourdomain.com {
    reverse_proxy localhost:6767
}
```

Nginx:
```nginx
server {
    listen 80;
    server_name stagedisplay.yourdomain.com;
    location / {
        proxy_pass http://localhost:6767;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

> `X-Forwarded-For` is required for IP-based campus routing to work correctly behind a proxy.

---

### NixOS Flake

The repo exports a NixOS module via its flake.

**1. Add the input to your `flake.nix`:**

```nix
inputs = {
  # ...
  stage-display.url = "github:TristonYoder/multi-campus-stage-display";
};
```

**2. Pass it through to your host outputs and import the module:**

```nix
# hosts/yourhost/configuration.nix
{ inputs, ... }: {
  imports = [ inputs.stage-display.nixosModules.default ];

  services.stage-display.enable = true;
  # services.stage-display.port = 6767;     # optional, default 6767
  # services.stage-display.dataDir = "..."; # optional
}
```

On first deploy, `campuses.json` is seeded from the repo into `dataDir`. `data.json` starts empty. Both files persist across updates.

**3. Expose via reverse proxy (optional):**

```nix
modules.services.vHosts.hosts."stage.yourdomain.com" = {
  reverseProxyPort = 6767;
};
```

---

## Python Dev Environment

### Prerequisites

- Python 3.10+
- Git

### Setup

**1. Clone the repo:**

```bash
git clone https://github.com/TristonYoder/multi-campus-stage-display.git
cd multi-campus-stage-display
```

**2. Create and activate a virtual environment:**

```bash
python3 -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
```

**3. Install dependencies:**

```bash
pip install flask
```

**4. Run the server:**

```bash
python3 server.py
# open http://localhost:6767
```

The server reads `campuses.json` and `data.json` from the project root. `data.json` is gitignored and will be created automatically on first save.

**macOS app dependencies (for building the menu bar app locally):**

```bash
pip install -r requirements-mac.txt
```

---

## Configuration Files

| File | Purpose |
|---|---|
| `campuses.json` | Campus names, slugs, IP ranges, and display slot definitions |
| `data.json` | Current content for each campus (gitignored) |

Both files are read on every request. In Docker they are volume-mounted so edits apply immediately without restarting the container.

---

## RSS Feed URLs

| Type | URL |
|---|---|
| Static (by campus) | `/rss/campus/host-pre-service` |
| Dynamic (by requestor IP) | `/rss/dynamic/host-pre-service` |

Slot slugs are defined in `campuses.json` and configurable via the Settings tab.

---

## URL Reference

| Purpose | URL |
|---|---|
| Editor UI | `http://SERVER_IP:6767` |
| Campus direct link | `http://SERVER_IP:6767/campus` |
| Static RSS feed | `http://SERVER_IP:6767/rss/campus/host-pre-service` |
| Dynamic RSS (by IP) | `http://SERVER_IP:6767/rss/dynamic/host-pre-service` |
