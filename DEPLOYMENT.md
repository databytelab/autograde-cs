# AutoGrade CS — deployment guide

Release: **v0.9.2-pilot** — a release candidate for a single-department pilot.

This describes the supported production deployment: one host, Docker
Compose, PostgreSQL, and a background grading worker. It is deliberately
small. There is no Kubernetes, no Redis, no message broker and no separate
frontend build, because at this scale each of those adds more failure modes
than it removes.

---

## 1. What runs

| Service | Image / build | Published | Purpose |
|---|---|---|---|
| `caddy` | `caddy:2.8-alpine` | **80, 443** | TLS, security headers, body limit. The only public entrypoint. |
| `frontend` | `docker/Dockerfile.frontend` | internal `8501` | Streamlit UI |
| `api` | `docker/Dockerfile.backend` | internal `8000` | FastAPI. Serves requests; runs migrations at start; never grades. |
| `worker` | `docker/Dockerfile.backend` | none | Claims grading jobs and runs them. The only process that calls the model provider. |
| `db` | `postgres:16-alpine` | none | PostgreSQL 16 |
| `backup` | `postgres:16-alpine` | none | Periodic `pg_dump` with retention |

Only Caddy is on the `edge` network. Everything else is on an `internal`
network with `internal: true`, so **PostgreSQL, the API and the worker are
not reachable from outside the host at all**. That is what makes the
`X-Forwarded-For` used by login throttling trustworthy — the API cannot be
called around the proxy.

### Persistent volumes

| Volume | Holds | Losing it means |
|---|---|---|
| `pgdata` | The gradebook: users, courses, rubrics, grades, jobs | Total data loss |
| `uploads` | Student submission files | Grades survive, original work does not |
| `backups` | `pg_dump` output | Falls back to the last off-host copy |
| `caddy_data` | TLS certificates | Certificates are re-issued (rate limits apply) |

`pgdata` and `uploads` are the two that matter. Back up both.

---

## 2. First deployment

```bash
git clone <your-remote> autograde && cd autograde
git checkout v0.9.2-pilot
cp .env.example .env
```

Fill in `.env`. The values that must change:

```bash
ENVIRONMENT=production
PUBLIC_HOSTNAME=autograde.your-university.edu
ACME_EMAIL=you@your-university.edu

# python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=<48+ random chars>
# python -c "import secrets; print(secrets.token_urlsafe(24))"
POSTGRES_PASSWORD=<random>

DATABASE_URL=postgresql+psycopg2://autograde:<POSTGRES_PASSWORD>@db:5432/autograde
CORS_ORIGINS=https://autograde.your-university.edu

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Then:

```bash
chmod 600 .env
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

The API applies migrations on start, so there is no separate migration step.
Watch it come up:

```bash
docker compose -f docker-compose.prod.yml logs -f api worker
```

Expect `app.started` from the API and `worker.started` from the worker.

**The API refuses to start** in `production` if `SECRET_KEY` is the default,
a placeholder or under 32 characters; if `DATABASE_URL` is SQLite or still
the development default; or if the selected provider has no usable key. A
refused boot is intentional — it is safer than a silently insecure service.

### Create the first account

Self sign-up is closed in production (`ALLOW_OPEN_REGISTRATION=false`, the
default). The one exception is the very first account, which becomes the
**administrator** — otherwise a fresh install could never be set up. Create
it immediately after deploying, before the URL is shared; every account
after it is created by that administrator, in the UI under **Settings →
Account → People** or through the same endpoint with their bearer token:

```bash
curl -sS https://<PUBLIC_HOSTNAME>/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@university.edu","name":"Your Name",
       "password":"<a long password>","role":"professor"}'
```

---

## 3. Environment variables

| Variable | Required | Notes |
|---|---|---|
| `ENVIRONMENT` | yes | `production` enables JSON logging and the safety gates |
| `SECRET_KEY` | yes | JWT signing key. Rotating it signs everyone out. |
| `DATABASE_URL` | yes | Must be PostgreSQL in production |
| `POSTGRES_PASSWORD` | yes | Compose refuses to start without it |
| `PUBLIC_HOSTNAME` | yes | Hostname Caddy serves and requests a certificate for |
| `ACME_EMAIL` | for real TLS | Expiry warnings. Leave blank for `localhost`. |
| `LLM_PROVIDER` | yes | `openai` \| `anthropic` \| `local` |
| `OPENAI_API_KEY` etc. | yes | Whichever the selected provider needs |
| `CORS_ORIGINS` | yes | Your public URL |
| `MAX_FILE_SIZE_MB` | no | Per-file upload cap (default 50) |
| `MAX_REQUEST_BODY_MB` | no | Whole-body cap, proxy and app (default 300) |
| `LLM_TIMEOUT_SECONDS` | no | Per model call (default 120) |
| `LLM_MAX_RETRIES` | no | SDK-level retries (default 3) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | Default 480 (8h) |
| `CANVAS_BASE_URL` / `CANVAS_API_TOKEN` | no | Without them, Canvas push is disabled; exports still work |
| `BACKUP_INTERVAL_HOURS` / `BACKUP_RETENTION_DAYS` | no | Default 24 / 30 |

---

## 4. Backups and restore

The `backup` service dumps the database every `BACKUP_INTERVAL_HOURS` into
the `backups` volume and deletes dumps older than `BACKUP_RETENTION_DAYS`.

```bash
docker compose -f docker-compose.prod.yml logs backup | tail
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups
```

### Copy backups off the host

A backup on the same disk as the database is not a backup. Add a cron job on
the host:

```cron
30 3 * * * docker run --rm -v autograde_backups:/b -v /srv/offsite:/out \
             alpine sh -c 'cp -u /b/*.dump /out/' >> /var/log/autograde-backup.log 2>&1
```

Also copy the `uploads` volume — student files are not in the database:

```bash
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/out \
  alpine tar czf /out/uploads-$(date +%F).tar.gz -C /u .
```

### Tested restore procedure

Run this once before term starts, on a throwaway copy. An untested backup is
a guess.

```bash
# 1. Stop everything that writes.
docker compose -f docker-compose.prod.yml stop api worker frontend

# 2. Pick a dump.
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups

# 3. Restore into a clean database. --clean drops existing objects first.
docker compose -f docker-compose.prod.yml exec backup \
  pg_restore -h db -U autograde -d autograde --clean --if-exists \
             /backups/autograde-<STAMP>.dump

# 4. Restore uploads if they were lost too.
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/in \
  alpine tar xzf /in/uploads-<DATE>.tar.gz -C /u

# 5. Bring it back.
docker compose -f docker-compose.prod.yml start api worker frontend
curl -sS https://<PUBLIC_HOSTNAME>/api/health
```

`/api/health` returns `database_ok: true` and HTTP 200 only when the database
actually answers, so it is a real post-restore check rather than a liveness
ping.

**Jobs that were running when the dump was taken** come back as `running`
with a stale heartbeat. The worker requeues them within a minute and grading
resumes; already-graded submissions are skipped, so the model is not paid
twice.

---

## 5. Upgrading

```bash
cd autograde
docker compose -f docker-compose.prod.yml exec backup \
  pg_dump -h db -U autograde -d autograde -Fc -f /backups/pre-upgrade-$(date +%F).dump

git fetch --tags && git checkout <new-tag>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api | head -40
```

Migrations run automatically as the API starts. Take the pre-upgrade dump
first — it is the rollback.

### Rollback

```bash
git checkout v0.9.2-pilot
docker compose -f docker-compose.prod.yml up -d --build
```

If the new version applied a migration that the old code cannot read, also
restore the pre-upgrade dump using the procedure in §4. Alembic downgrades
are **not** relied on for rollback; the dump is the mechanism.

---

## 6. Operations

### Grading jobs

Grading is asynchronous. `POST /api/assignments/{id}/grade` returns **202**
with a job; the UI polls `GET /api/jobs/{id}`. A run survives a browser
refresh, a page close and an application restart.

```bash
# What is the queue doing?
docker compose -f docker-compose.prod.yml exec db \
  psql -U autograde -c \
  "SELECT id, status, processed, total, attempts, updated_at
     FROM grading_jobs ORDER BY created_at DESC LIMIT 10;"

# More grading throughput (claiming is transactional; workers do not collide)
docker compose -f docker-compose.prod.yml up -d --scale worker=3
```

A second grading request for an assignment that is already queued or running
returns **409**. That is enforced by a partial unique index, not just an
application check, so a double-click cannot slip past it.

### Logs

Production logs are one JSON object per line. Useful event prefixes:

| Prefix | Covers |
|---|---|
| `auth.*` | `login_failed`, `login_succeeded`, `throttled` |
| `grading_job.*` | `enqueued`, `claimed`, `completed`, `failed`, `stale` |
| `worker.*` | `started`, `reaped_stale_jobs`, `loop_error` |
| `http.body_too_large` | Rejected over-sized requests |

```bash
docker compose -f docker-compose.prod.yml logs api \
  | grep '"event":"auth.login_failed"'
```

Passwords, API keys, and submission content are never logged. Email
addresses in auth events are a salted hash, so repeated failures can be
correlated without writing addresses into a log aggregator.

### Login throttling

8 failures per account and 30 per client address in 15 minutes, then HTTP
429 with `Retry-After`. Counted in the database, so it holds across restarts
and across multiple API workers. A successful sign-in clears that account's
failures.

---

## 7. Remaining risks

| Risk | Mitigation now | Fix if it becomes real |
|---|---|---|
| **Prompt injection** — students author the text that goes to the grader | System prompt fences the submission and flags attempts as `prompt_injection`; instructor approves every grade | Treat the flag as a must-review queue |
| **No reset-by-email** — a forgotten password needs the administrator | Administrators reset passwords and deactivate accounts in the UI | SSO, once a university identity provider is available |
| **Tokens cannot be revoked** before their 8h expiry | Short-ish expiry; staff-only accounts | Server-side session table |
| **One host** — no redundancy | Backups, `restart: unless-stopped` | A second host, or accept the downtime |
| **Model spend** is unbounded per run | Job counters make cost visible per assignment | A per-course budget cap |
| **`uploads` is a local volume** — one host only | Fine for a single instance | S3-compatible storage before scaling out |
| **Streamlit holds session state in the process** | Fine for a handful of staff | A real frontend when concurrent *users*, not submissions, are the constraint |
| **No automated dependency scanning** | Pins are current; `python-jose` pinned ≥3.4.0 for CVE-2024-33664 | Add `pip-audit` to CI |

---

## 8. Local development

Unchanged and still SQLite — no Postgres needed to work on the code.

```bash
python -m venv venv && venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env                             # ENVIRONMENT=development

alembic upgrade head
uvicorn backend.main:app --reload                # API
python -m backend.worker                         # worker, second terminal
streamlit run frontend_streamlit/app.py          # UI, third terminal
```

Without a worker running, grading jobs stay `queued` — which is the expected
behaviour, not a bug.

```bash
pytest -q          # 309 tests, no network and no API key required
```
