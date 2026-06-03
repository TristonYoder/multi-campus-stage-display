# Campus Stage Displays

[![Build & Push Docker Image](https://github.com/TristonYoder/stage-display-content/actions/workflows/docker.yml/badge.svg)](https://github.com/TristonYoder/stage-display-content/actions/workflows/docker.yml)

A web app for managing ProPresenter stage display content across multiple campuses. Each campus has editable display slots (Host-Pre, Host-Mid, Host-Post) served as RSS feeds — consumed directly by ProPresenter's stage display.

## Features

- **Multi-campus tabs** — Easily add your campuses to the database
- **RSS feeds** per campus and slot, plus a dynamic feed that routes by requesting IP for unified ProPresenter configs
- **ProPresenter Config tab** — copy RSS URLs ready to paste into ProPresenter
- **Settings tab** — add/remove campuses and display types without touching config files
- **Direct URLs** — `/campus-name` opens straight to that campus tab

---

## Quick start (local)

```bash
python3 -m pip install flask
python3 server.py
# open http://localhost:7474
```

---

## Docker (local)

```bash
docker compose up -d
# open http://localhost:7474
```

---

## Deployment

The image is built automatically on every push to `main` and published to:

```
ghcr.io/tristonyoder/stage-display-content:latest
```

### 1. Make the package public (one-time)

1. Go to [github.com/TristonYoder](https://github.com/TristonYoder) → **Packages** → `stage-display-content`
2. **Package settings** → Change visibility → **Public**

Or leave it private and run `docker login ghcr.io` on each server before pulling.

### 2. Set up the server (first time only)

```bash
mkdir -p /opt/stage-display && cd /opt/stage-display
echo '{}' > data.json
curl -o campuses.json \
  https://raw.githubusercontent.com/TristonYoder/stage-display-content/main/campuses.json
```

Create `docker-compose.yml`:

```yaml
services:
  stage-display:
    image: ghcr.io/tristonyoder/stage-display-content:latest
    ports:
      - "7474:7474"
    volumes:
      - ./campuses.json:/app/campuses.json
      - ./data.json:/app/data.json
    restart: always
```

```bash
docker compose pull && docker compose up -d
```

### 3. Updating

```bash
cd /opt/stage-display
docker compose pull && docker compose up -d
```

### 4. Automatic updates with Watchtower

Add to `docker-compose.yml` to poll for new images every 5 minutes:

```yaml
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 stage-display-stage-display-1
```

### 5. Reverse proxy (optional)

**Caddyfile:**
```
stagedisplay.yourdomain.com {
    reverse_proxy localhost:7474
}
```

**Nginx:**
```nginx
server {
    listen 80;
    server_name stagedisplay.yourdomain.com;
    location / {
        proxy_pass http://localhost:7474;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

> `X-Forwarded-For` is required for dynamic RSS IP routing to work correctly behind a proxy.

---

## RSS feed URLs

| Type | URL |
|---|---|
| Static (by campus) | `/rss/fishers/host-pre` |
| Dynamic (by requestor IP) | `/rss/dynamic/host-pre` |

Slots: `host-pre` · `host-mid` · `host-post`

---

## Configuration

| File | Purpose |
|---|---|
| `campuses.json` | Campus names, slugs, IP ranges, and display slot definitions |
| `data.json` | Current content for each campus (gitignored) |

Both files are volume-mounted in Docker and read on every request — edit them on disk and changes apply immediately.

---

## URL reference

| Purpose | URL |
|---|---|
| Editor UI | `http://SERVER_IP:7474` |
| Campus direct link | `http://SERVER_IP:7474/fishers` |
| Static RSS feed | `http://SERVER_IP:7474/rss/fishers/host-pre` |
| Dynamic RSS (by IP) | `http://SERVER_IP:7474/rss/dynamic/host-pre` |
