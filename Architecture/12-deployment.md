# Deployment

---

## Production Architecture

```
Internet
   │  HTTPS (443) / HTTP (80 → 308 redirect)
   ▼
┌──────────────────────────────────────────┐
│  Caddy (reverse proxy + TLS)             │
│  • Auto Let's Encrypt certs              │
│  • HTTPS enforced, HSTS                  │
│  • Serves frontend static files          │
│  • Proxies /api/* → backend:8000         │
└──────────────────┬───────────────────────┘
                   │ Docker internal network
                   ▼
┌──────────────────────────────────────────┐
│  Backend (Uvicorn, --workers 1)          │
│  port 8000 — NOT exposed externally      │
└──────────────────────────────────────────┘
         │
         ▼
  /app/data/space_adventures.db  (named Docker volume)
```

The frontend is **not a running container**. It is built to static files (`npm run build`) and served directly by Caddy. Only 2 containers run in production: **Caddy** and **Backend**.

---

## Dockerfiles

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Required for bcrypt C extension (P35)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev python3-dev gcc curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

RUN mkdir -p /app/data  # P31 — SQLite data directory must exist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### `frontend/Dockerfile` (multi-stage, for CI builds)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
RUN npm run build

FROM scratch AS dist
COPY --from=builder /app/dist /dist
```

In practice: build the frontend on the host or in CI; bind-mount `dist/` into Caddy.

### `frontend/Dockerfile.dev`

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm ci
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## Caddyfile

```caddy
{
    email {$CADDY_TLS_EMAIL}
}

{$APP_DOMAIN} {
    encode gzip zstd

    header {
        Strict-Transport-Security  "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options     "nosniff"
        X-Frame-Options            "DENY"
        X-XSS-Protection           "1; mode=block"
        Referrer-Policy            "strict-origin-when-cross-origin"
        Permissions-Policy         "geolocation=(self)"
        Content-Security-Policy    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'"
        -Server
    }

    # Strip sensitive headers from access logs
    log {
        format filter {
            wrap json
            fields {
                request>headers>Authorization delete
                request>headers>X-Admin-Key delete
            }
        }
    }

    reverse_proxy /api/* backend:8000 {
        health_uri      /api/v1/health
        health_interval 30s
    }

    root * /srv
    try_files {path} /index.html
    file_server
}
```

---

## docker-compose.yml (Development Only)

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports: ["8000:8000"]
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
    env_file: .env
    volumes:
      - ./backend/app:/app/app    # source only — does NOT overwrite site-packages (P30)
      - sa_db_data:/app/data

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports: ["5173:5173"]
    environment:
      - VITE_API_BASE_URL=http://localhost:8000
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
    depends_on: [backend]

volumes:
  sa_db_data:
```

Localhost is exempt from HTTPS — Geolocation API works in dev without TLS.

---

## docker-compose.prod.yml (Production)

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      - APP_DOMAIN=${APP_DOMAIN}
      - CADDY_TLS_EMAIL=${CADDY_TLS_EMAIL}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/srv:ro
      - caddy_data:/data       # TLS certs — NEVER delete this volume
      - caddy_config:/config
    depends_on:
      backend:
        condition: service_healthy

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
    env_file: .env.prod
    volumes:
      - sa_db_data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    # No ports: — backend is internal only

volumes:
  caddy_data:
  caddy_config:
  sa_db_data:
```

---

## Environment Files

### `.env.example` (development)

```dotenv
NASA_API_KEY=DEMO_KEY
N2YO_API_KEY=
LL2_API_KEY=
LL2_SYNC_INTERVAL_MINUTES=30
JWT_SECRET_KEY=dev_jwt_secret_change_in_prod
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
UNSUBSCRIBE_SECRET_KEY=dev_unsub_secret_change_in_prod
ADMIN_API_KEY=dev_admin_key
N2YO_QUOTA_CAP=900
DATABASE_URL=sqlite+aiosqlite:///./data/space_adventures.db
DATABASE_URL_SYNC=sqlite:///./data/space_adventures.db
CORS_ORIGINS=http://localhost:5173
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@localhost
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

### `.env.prod.example` (production — all values mandatory)

```dotenv
APP_DOMAIN=space-adventures.example.com
CADDY_TLS_EMAIL=admin@example.com

NASA_API_KEY=your_registered_nasa_api_key
N2YO_API_KEY=your_n2yo_api_key
LL2_API_KEY=
LL2_SYNC_INTERVAL_MINUTES=30

# Generate: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
UNSUBSCRIBE_SECRET_KEY=
ADMIN_API_KEY=

N2YO_QUOTA_CAP=900
DATABASE_URL=sqlite+aiosqlite:///./data/space_adventures.db
DATABASE_URL_SYNC=sqlite:///./data/space_adventures.db
CORS_ORIGINS=https://space-adventures.example.com

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=
SMTP_FROM=noreply@space-adventures.example.com

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

---

## First Deployment Runbook

Prerequisites: Docker ≥ 26, ports 80 and 443 open, DNS pointing at server's IP.

**Step 1 — Clone and configure**
```bash
git clone <repo-url> space-adventures && cd space-adventures
cp .env.prod.example .env.prod
chmod 600 .env.prod   # -rw------- only
# Fill all values; generate secrets with: python -c "import secrets; print(secrets.token_hex(32))"
# .env.prod must be in .gitignore — never commit it
```

**Step 2 — Build frontend**
```bash
cd frontend && npm ci
VITE_API_BASE_URL=https://<APP_DOMAIN> npm run build
ls dist/index.html   # must exist
cd ..
```

**Step 3 — Run migrations**
```bash
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

**Step 4 — Start stack**
```bash
docker compose -f docker-compose.prod.yml up -d
```

**Step 5 — Verify**
```bash
curl -sf https://<APP_DOMAIN>/api/v1/health | python -m json.tool
curl -sv https://<APP_DOMAIN> 2>&1 | grep "SSL certificate"
docker compose -f docker-compose.prod.yml logs --tail=50
```

Caddy provisions the Let's Encrypt cert on first request (5–30 seconds). If it fails: check DNS resolves and port 80 is reachable.

---

## Redeployment

```bash
git pull

# Backend changed:
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml up -d backend
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# Frontend changed:
cd frontend && npm ci
VITE_API_BASE_URL=https://<APP_DOMAIN> npm run build && cd ..
# Caddy picks up new files immediately — no restart needed
```

---

## TLS Notes

- **Never delete `caddy_data` volume** — Let's Encrypt rate-limits to 5 duplicate certs/week.
- Caddy auto-renews ≥ 30 days before expiry.
- **Do NOT submit to the HSTS preload list (`hstspreload.org`) during initial deployment.** Wait at least one month of stable HTTPS. Once preloaded, browsers refuse HTTP for up to 1 year — if HTTPS breaks, the domain becomes inaccessible with no emergency workaround.
- `Permissions-Policy: geolocation=(self)` — only the app's own origin can request geolocation.
