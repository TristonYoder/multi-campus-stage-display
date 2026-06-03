# Campus Stage Displays

[![Build & Push Docker Image](https://github.com/TristonYoder/stage-display-content/actions/workflows/docker.yml/badge.svg)](https://github.com/TristonYoder/stage-display-content/actions/workflows/docker.yml)

A web app for managing ProPresenter stage display content across multiple campuses. Each campus has editable display slots (Host-Pre, Host-Mid, Host-Post) served as RSS feeds — consumed directly by ProPresenter's stage display.

## Features

- **Multi-campus tabs** — Easilly add your campuses to the database
- **RSS feeds** per campus and slot, plus a dynamic feed that routes by requesting IP for unified ProPresenter configs
- **ProPresenter Config tab** — copy RSS URLs ready to paste into ProPresenter
- **Settings tab** — add/remove campuses and display types without touching config files
- **Direct URLs** — `/campus-name` opens straight to that campus tab

## Quick start (local)

```bash
python3 -m pip install flask
python3 server.py
# open http://localhost:7474
```

## Docker

```bash
docker compose up -d
# open http://localhost:7474
```

## RSS feed URLs

| Type | URL |
|---|---|
| Static (by campus) | `/rss/fishers/host-pre` |
| Dynamic (by requestor IP) | `/rss/dynamic/host-pre` |

Slots: `host-pre` · `host-mid` · `host-post`

## Configuration

| File | Purpose |
|---|---|
| `campuses.json` | Campus names, slugs, IP ranges, and display slot definitions |
| `data.json` | Current content for each campus (gitignored) |

Both files are volume-mounted in Docker and read on every request — edit them on disk and changes apply immediately.

## Deployment

See [DEPLOY.md](DEPLOY.md) for full server deployment instructions including reverse proxy setup and auto-updates with Watchtower.
