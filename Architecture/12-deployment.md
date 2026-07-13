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
└──────────────────┬───────────────────────┘
                   │ Docker internal network
                   ▼
┌──────────────────────────────────────────┐
│  Postgres 17 (db)                        │
│  port 5432 — NOT exposed externally      │
└──────────────────────────────────────────┘
         │
         ▼
     pg_data  (named Docker volume)
```

SQLite remains the local-dev default (zero-setup) — see `16-postgres-migration.md`.
Production and CI run Postgres.

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

    # Global API rate limiting — prevents abuse of data endpoints that have no application-level limits.
    # Requires the caddy-ratelimit module: add to Caddy build or use xcaddy.
    # Adjust `events` and `window` based on observed traffic.
    @api path /api/*
    rate_limit @api {
        zone api_global {
            key     {remote_host}
            events  120
            window  1m
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
    environment:
      # Built here, not left as a literal ${POSTGRES_PASSWORD} inside
      # .env.prod — env_file: values are passed through verbatim, docker
      # compose only expands ${...} in the compose file itself.
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      - DATABASE_URL_SYNC=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    # No ports: — backend is internal only
    # No sa_db_data volume — the app is stateless; all data lives in Postgres (db).

  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    # No ports: — only reachable from other containers on the compose network

volumes:
  caddy_data:
  caddy_config:
  pg_data:
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

# Generate each with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=1209600
UNSUBSCRIBE_SECRET_KEY=
ADMIN_API_KEY=

N2YO_QUOTA_CAP=900
# Prod and CI run Postgres (16-postgres-migration.md); `db` is the compose
# service name — resolves on the Docker internal network only.
# DATABASE_URL / DATABASE_URL_SYNC are NOT set here — env_file: values are
# not ${...}-expanded by docker compose, so they're built from these three
# vars directly in docker-compose.prod.yml's backend service instead.
POSTGRES_USER=sa
POSTGRES_PASSWORD=
POSTGRES_DB=space_adventures
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
FRONTEND_ORIGIN=https://space-adventures.example.com

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=
SMTP_FROM=noreply@space-adventures.example.com

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

APP_REQUIRE_SECRETS=1
COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
EXPOSE_DOCS=false
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

**Step 3 — Start the database and run migrations**
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d db
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

**Step 4 — Start stack**
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

**Step 5 — Verify**
```bash
curl -sf https://<APP_DOMAIN>/api/v1/health | python -m json.tool
curl -sv https://<APP_DOMAIN> 2>&1 | grep "SSL certificate"
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=50
```

Caddy provisions the Let's Encrypt cert on first request (5–30 seconds). If it fails: check DNS resolves and port 80 is reachable.

---

## Backup & Restore Runbook (P2.6)

Nightly logical backups of the Postgres `db` service, run from the **host**
(a cron job or systemd timer calling `docker compose exec`), never from an
in-container crond — the host is what survives a container being recreated,
and it's the one place with the object-storage credentials.

**Nightly backup (host cron / systemd timer)**

```bash
#!/usr/bin/env bash
# /opt/space-adventures/backup.sh — run nightly at 03:00 server time.
set -euo pipefail

cd /opt/space-adventures
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="/opt/space-adventures/backups/space_adventures_${STAMP}.dump"

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" > "$DUMP"

# Upload to object storage (adjust for the provider actually in use).
aws s3 cp "$DUMP" "s3://space-adventures-backups/$(basename "$DUMP")"

# 30-day retention, both locally and in the bucket.
find /opt/space-adventures/backups -name '*.dump' -mtime +30 -delete
aws s3api list-objects-v2 --bucket space-adventures-backups \
  --query "Contents[?LastModified<='$(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ)'].Key" \
  --output text | xargs -r -n1 -I{} aws s3 rm "s3://space-adventures-backups/{}"
```

Crontab entry (`crontab -e` for the deploy user, or a systemd timer with the
same schedule):

```
0 3 * * * /opt/space-adventures/backup.sh >> /var/log/sa-backup.log 2>&1
```

`pg_dump -Fc` (custom format) is used rather than plain SQL so `pg_restore`
can do a parallel, selective restore and so the dump is compressed on disk.

**Restore rehearsal (rehearse once before beta, and after any major version
bump of Postgres)**

1. **Drop the DB** (on a disposable staging stack — never rehearse against
   the live prod volume):
   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml stop backend
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
     dropdb -U "$POSTGRES_USER" "$POSTGRES_DB"
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
     createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"
   ```
2. **Restore the dump**:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml cp \
     backups/space_adventures_<STAMP>.dump db:/tmp/restore.dump
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
     pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
     /tmp/restore.dump
   ```
3. **App healthy**: bring the backend back up and confirm the same health
   check used in the deployment runbook (Step 5 above) passes, and that a
   spot-checked row count (e.g. `SELECT count(*) FROM users;`) matches the
   pre-drop expectation:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml start backend
   curl -sf https://<APP_DOMAIN>/api/v1/health | python -m json.tool
   ```

Record the date and outcome of each rehearsal here once performed:

| Date | Rehearsed by | Result |
| --- | --- | --- |
| _(pending — schedule before beta, per L3 pre-launch gates)_ | | |

---

## Email Deliverability Checklist (P1.8)

Run once, before the first production notification email goes out. Gmail/Yahoo
silently foldered mail is a broken product — this is not optional.

- [ ] Transactional SMTP provider configured (Postmark or SES), `SMTP_HOST` /
      `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` point at it — not a personal
      mailbox.
- [ ] Provider's DKIM keys installed as DNS TXT records for the sending
      domain.
- [ ] SPF record includes the provider's sending host
      (`v=spf1 include:<provider> ~all`).
- [ ] DMARC record published at `p=none` initially:
      `v=DMARC1; p=none; rua=mailto:dmarc-reports@<domain>`.
- [ ] After one clean week (no unexpected DMARC failures in the aggregate
      reports), tighten to `p=quarantine`.
- [ ] `List-Unsubscribe` / `List-Unsubscribe-Post: List-Unsubscribe=One-Click`
      headers verified present on a live test send (`notification_service._send_email`
      sets these; see `tests/test_notifications.py::test_email_includes_list_unsubscribe_headers`).

---

## Secret Rotation Runbook

Rotate immediately on suspected compromise; rotate proactively on a schedule
otherwise (annually at minimum). See root `SECURITY.md` for the disclosure
process this supports.

| Secret | Rotation procedure |
|---|---|
| `JWT_SECRET_KEY` | Set new value in `.env.prod`, redeploy backend. Invalidates all outstanding access/refresh tokens — every user is logged out. |
| `UNSUBSCRIBE_SECRET_KEY` | Set new value, redeploy. Invalidates outstanding unsubscribe links (30-day TTL) — acceptable, they regenerate on the next notification email. |
| `ADMIN_API_KEY` | Set new value, redeploy, update any external caller (monitoring scripts). |
| VAPID keys (Web Push) | Regenerate, redeploy. Existing push subscriptions become invalid — clients re-subscribe on next visit. |
| `DEEPL_API_KEY` | Rotate in the DeepL dashboard, update `.env.prod`, redeploy. No user-facing invalidation. |
| SMTP credentials | Rotate with the provider (Postmark/SES), update `.env.prod`, redeploy. |
| Twilio credentials | Rotate in the Twilio console, update `.env.prod`, redeploy. |
| Social/bot API tokens | Rotate with the provider, update `.env.prod`, redeploy. |

**Compromised dependency response:** pin the affected package to the last
known-good version, run `pip-audit` / `npm audit` to confirm the fix, rotate
any secret the dependency could plausibly have exfiltrated, and — if user data
may have been touched — notify per PIPEDA's breach-notification duty (the
operator is Canadian).

---

## Redeployment

```bash
git pull

# Backend changed:
docker compose --env-file .env.prod -f docker-compose.prod.yml build backend
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d backend
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm backend alembic upgrade head

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
