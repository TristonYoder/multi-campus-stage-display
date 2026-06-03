# Deployment

## Prerequisites

- Docker + Docker Compose on the target server

The image is built automatically on every push to `main` and published to:

```
ghcr.io/tristonyoder/stage-display-content:latest
```

---

## 1. Make the package public (one-time)

1. Go to [github.com/TristonYoder](https://github.com/TristonYoder) → **Packages** → `stage-display-content`
2. **Package settings** → Change visibility → **Public**

Or leave it private and run `docker login ghcr.io` on each server before pulling.

---

## 2. Deploy on a server

### a) Create the data directory (first time only)

```bash
mkdir -p /opt/stage-display && cd /opt/stage-display
echo '{}' > data.json
```

Download the default campus config:

```bash
curl -o campuses.json \
  https://raw.githubusercontent.com/TristonYoder/stage-display-content/main/campuses.json
```

### b) Create `docker-compose.yml`

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

### c) Pull and start

```bash
docker compose pull && docker compose up -d
```

The app is now running at `http://SERVER_IP:7474`.

---

## 3. Updating

Every push to `main` rebuilds the image. To deploy on the server:

```bash
cd /opt/stage-display
docker compose pull && docker compose up -d
```

### Automatic updates with Watchtower

Add to `docker-compose.yml` to poll for new images every 5 minutes:

```yaml
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 stage-display-stage-display-1
```

---

## 4. Reverse proxy (optional)

To serve on port 80/443, put Nginx or Caddy in front.

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

## URL reference

| Purpose | URL |
|---|---|
| Editor UI | `http://SERVER_IP:7474` |
| Campus direct link | `http://SERVER_IP:7474/fishers` |
| Static RSS feed | `http://SERVER_IP:7474/rss/fishers/host-pre` |
| Dynamic RSS (by IP) | `http://SERVER_IP:7474/rss/dynamic/host-pre` |
