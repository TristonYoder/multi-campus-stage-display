# Deployment

## Prerequisites

- Docker + Docker Compose on the target server
- A GitHub repo with this code pushed to `main`

---

## 1. Push to GitHub

```bash
git init
git remote add origin https://github.com/YOUR_ORG/stage-display-content.git
git add .
git commit -m "initial commit"
git push -u origin main
```

The GitHub Action (`.github/workflows/docker.yml`) triggers on every push to `main` and publishes the image to:

```
ghcr.io/YOUR_ORG/stage-display-content:latest
```

No secrets to configure — the workflow uses the built-in `GITHUB_TOKEN`.

---

## 2. Make the package public (one-time)

After the first successful build:

1. Go to **github.com/YOUR_ORG** → **Packages** → `stage-display-content`
2. **Package settings** → Change visibility → **Public**

Or leave it private and add `docker login ghcr.io` credentials on each server (see step 3b).

---

## 3. Deploy on a server

### a) Create the data files (first time only)

```bash
mkdir -p /opt/stage-display
cd /opt/stage-display

# Persistent config and content
cp /path/to/campuses.json .
echo '{}' > data.json
```

### b) Create `docker-compose.yml`

```yaml
services:
  stage-display:
    image: ghcr.io/YOUR_ORG/stage-display-content:latest
    ports:
      - "7474:7474"
    volumes:
      - ./campuses.json:/app/campuses.json
      - ./data.json:/app/data.json
    restart: always
```

### c) Pull and start

```bash
cd /opt/stage-display
docker compose pull
docker compose up -d
```

The app is now running at `http://SERVER_IP:7474`.

---

## 4. Updating

Every push to `main` rebuilds the image. To deploy the update on the server:

```bash
cd /opt/stage-display
docker compose pull
docker compose up -d
```

Or automate it with [Watchtower](https://containrrr.dev/watchtower/):

```yaml
# add to docker-compose.yml
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 stage-display-stage-display-1
```

---

## 5. Reverse proxy (optional)

To serve on port 80/443, put Nginx or Caddy in front:

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

> The `X-Forwarded-For` header is required for dynamic RSS IP routing to work correctly behind a proxy.

---

## Ports & URLs

| Purpose | URL |
|---|---|
| Editor UI | `http://SERVER_IP:7474` |
| Campus direct link | `http://SERVER_IP:7474/fishers` |
| Static RSS feed | `http://SERVER_IP:7474/rss/fishers/host-pre` |
| Dynamic RSS (by IP) | `http://SERVER_IP:7474/rss/dynamic/host-pre` |
