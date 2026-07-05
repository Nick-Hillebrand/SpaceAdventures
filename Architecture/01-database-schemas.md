# Database Schemas

All tables use SQLAlchemy 2 async ORM. SQLite for dev, PostgreSQL for prod (swap via DATABASE_URL env var).

**Critical SQLite requirements** (add to `database.py`):
- Enable FK enforcement: `PRAGMA foreign_keys = ON` via an engine connect event listener.
- Use `server_default=text("CURRENT_TIMESTAMP")` — NOT `server_default=func.now()` (SQLite does not have `NOW()`).
- Alembic migrations must use the **sync** URL (`DATABASE_URL_SYNC`), not the async URL.
- After every `op.create_table()` in a migration, manually add `CHECK` constraints — Alembic autogenerate silently omits them on SQLite.

---

## NASA Cache Tables

### `apod` table
```
date           TEXT  PRIMARY KEY  -- YYYY-MM-DD, canonical cache key
title          TEXT
explanation    TEXT
url            TEXT
hdurl          TEXT  NULLABLE
media_type     TEXT  -- "image" or "video"
copyright      TEXT  NULLABLE
thumbnail_url  TEXT  NULLABLE     -- for video APODs
fetched_at     DATETIME
```

### `neo` table
One row per NEO per close-approach date:
```
id                        TEXT  PRIMARY KEY  -- NASA NEO ID
name                      TEXT
close_approach_date        TEXT              -- YYYY-MM-DD
absolute_magnitude_h       REAL
estimated_diameter_min_km  REAL
estimated_diameter_max_km  REAL
is_potentially_hazardous   BOOLEAN
relative_velocity_kph      REAL
miss_distance_km           REAL
orbiting_body              TEXT
nasa_jpl_url               TEXT
fetched_at                 DATETIME
```

### `space_weather_event` table
```
id           TEXT     PRIMARY KEY  -- event ID from DONKI
event_type   TEXT     CHECK IN ('FLR','GST','RBE','SEP','CME')
start_date   TEXT     -- YYYY-MM-DD, used for cache lookup
raw_json     TEXT     -- full JSON from DONKI stored as string
fetched_at   DATETIME
```

### `mars_photo` table
```
id           INTEGER  PRIMARY KEY  -- NASA photo ID
sol          INTEGER
earth_date   TEXT
rover_name   TEXT
camera_name  TEXT
img_src      TEXT
fetched_at   DATETIME
UNIQUE (rover_name, sol, camera_name, id)
```

---

## ISS / N2YO Tables

### `iss_position_batch` table
Stores the full 300-entry batch as JSON. One row; overwritten on each refresh.
```
id          INTEGER  PRIMARY KEY DEFAULT 1
positions   TEXT     -- JSON array of position objects (timestamp_ms, satlatitude, satlongitude, sataltitude, azimuth, elevation, ra, dec, eclipsed)
fetched_at  DATETIME
```

### `iss_tle` table
```
id          INTEGER  PRIMARY KEY DEFAULT 1
tle_line0   TEXT
tle_line1   TEXT
tle_line2   TEXT
fetched_at  DATETIME
```

### `iss_passes` table
```
id              INTEGER  PRIMARY KEY
pass_type       TEXT     CHECK IN ('visual','radio')
observer_lat    REAL
observer_lng    REAL
observer_alt    REAL
passes_json     TEXT     -- JSON array of pass objects
fetched_at      DATETIME
UNIQUE (pass_type, observer_lat, observer_lng, observer_alt)
```

### `n2yo_quota` table
Exactly one row; tracks the rolling hourly window.
```
id           INTEGER  PRIMARY KEY DEFAULT 1
window_start DATETIME
used         INTEGER  DEFAULT 0
```

---

## Launch Tables

### `launches` table
```
ll2_id              TEXT  PRIMARY KEY  -- UUID from LL2
name                TEXT              -- max 200 chars
net                 DATETIME          -- No Earlier Than (UTC)
status_abbrev       TEXT              -- Go, TBD, Hold, Gone, etc.
status_name         TEXT
agency_name         TEXT
agency_type         TEXT
rocket_name         TEXT
rocket_family       TEXT
mission_name        TEXT  NULLABLE
mission_description TEXT  NULLABLE    -- max 2000 chars
mission_type        TEXT  NULLABLE
pad_name            TEXT
pad_location        TEXT
image_url           TEXT  NULLABLE
livestream_urls     TEXT              -- JSON array of {title, url, feature_image}
fetched_at          DATETIME
```

---

## Auth Tables

### `users` table
```
id             INTEGER  PRIMARY KEY
first_name     TEXT     NOT NULL
last_name      TEXT     NOT NULL
email          TEXT     UNIQUE NULLABLE
phone          TEXT     UNIQUE NULLABLE
password_hash  TEXT     NOT NULL       -- bcrypt, cost ≥ 12; NEVER store plaintext
email_verified BOOLEAN  DEFAULT FALSE
phone_verified BOOLEAN  DEFAULT FALSE
created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
```
Constraint: at least one of `email` or `phone` must be non-null (enforced in the router, not just DB).

### `otps` table
```
id              INTEGER  PRIMARY KEY
user_id         INTEGER  FK → users.id  ON DELETE CASCADE
channel         TEXT     CHECK IN ('email','phone')
code_hash       TEXT     NOT NULL       -- bcrypt hash; never store the plaintext code
expires_at      DATETIME NOT NULL       -- NOW + 10 minutes
used            BOOLEAN  DEFAULT FALSE  -- set atomically in same transaction; prevents replay
failed_attempts INTEGER  DEFAULT 0     -- delete row after 5 wrong attempts (brute-force guard)
created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
```
Rate limits: max 5 rows per `(user_id, channel)` per hour (send rate); max 5 wrong attempts per row (attempt rate).

### `refresh_tokens` table
```
id           INTEGER  PRIMARY KEY
user_id      INTEGER  FK → users.id  ON DELETE CASCADE
token_hash   TEXT     NOT NULL       -- SHA-256 of raw token; raw token never stored
expires_at   DATETIME NOT NULL       -- NOW + 30 days
revoked      BOOLEAN  DEFAULT FALSE
created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
```
Rotation: on each `/auth/refresh`, issue a new token and set old `revoked = TRUE` in the same transaction using `SELECT … FOR UPDATE` (PostgreSQL) or asyncio.Lock (SQLite).

### `login_attempts` table
```
id           INTEGER  PRIMARY KEY
identifier   TEXT     NOT NULL  -- SHA-256 of the submitted email/phone; never store plaintext
ip_address   TEXT     NOT NULL
failed_at    DATETIME DEFAULT CURRENT_TIMESTAMP
```
Logic: count rows for `(identifier, ip_address)` in last 15 minutes. If ≥ 5 → return 429 with `Retry-After`. Delete rows for `identifier` on successful login.

---

## Subscription & Notification Tables

### `subscriptions` table
```
id           TEXT     PRIMARY KEY DEFAULT (lower(hex(randomblob(16))))  -- UUID, prevents enumeration
user_id      INTEGER  FK → users.id  ON DELETE CASCADE
type         TEXT     CHECK IN ('launch','agency')
ll2_id       TEXT     NULLABLE  -- set when type = 'launch'
agency_name  TEXT     NULLABLE  -- set when type = 'agency'
notify_email BOOLEAN  DEFAULT FALSE  -- must be explicitly set by user; only effective if email_verified
notify_sms   BOOLEAN  DEFAULT FALSE  -- must be explicitly set by user; only effective if phone_verified
created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
UNIQUE (user_id, type, ll2_id)
UNIQUE (user_id, type, agency_name)
```

### `pending_notifications` table
```
id              INTEGER  PRIMARY KEY
subscription_id TEXT     FK → subscriptions.id  ON DELETE CASCADE
ll2_id          TEXT
change_type     TEXT     CHECK IN ('NET_SLIP','STATUS_CHANGE','NEW_LAUNCH')
old_value       TEXT
new_value       TEXT
attempt_count   INTEGER  DEFAULT 0  -- delete after 3 failures
created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
```

### `notification_log` table
```
id               INTEGER  PRIMARY KEY
user_id          INTEGER  FK → users.id
ll2_id           TEXT
change_type      TEXT
channel          TEXT     CHECK IN ('email','sms')
delivery_status  TEXT     CHECK IN ('sent','failed')
error_detail     TEXT     NULLABLE  -- scrubbed: exception type + message only; passwords/tokens redacted with [REDACTED]
sent_at          DATETIME
```
