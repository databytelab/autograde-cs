# Running AutoGrade, and sharing it with colleagues

A practical guide for the person who runs the server. It assumes no prior
Docker knowledge and gives exact commands. Your colleagues need none of
this — they get a link and a password (see §7).

`DEPLOYMENT.md` is the architectural reference; this is the operating
manual.

---

## 1. What you need

| | Why |
|---|---|
| A computer or VM that stays on | Grading runs on the server, not on anyone's laptop |
| **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux) | Runs all six services |
| An OpenAI or Anthropic API key **or** Ollama | Something has to do the grading |
| ~4 GB RAM, ~10 GB disk | Comfortable for a department |

Install Docker from <https://docs.docker.com/get-docker/>, then confirm:

```bash
docker --version
docker compose version
```

Both must print a version. On Windows, Docker Desktop must be **running**
(whale icon in the system tray) before any command below will work.

> **Port check.** AutoGrade wants ports **80** and **443**. On this machine
> they are currently taken by Apache (XAMPP). Either stop that service, or
> change the ports — see §9.

---

## 2. First-time setup

```bash
git clone <your-repository-url> autograde
cd autograde
cp .env.example .env
```

Now generate two secrets and open `.env` in any text editor:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

Set at minimum:

```bash
ENVIRONMENT=production
PUBLIC_HOSTNAME=autograde.your-university.edu   # or `localhost` to try it out
ACME_EMAIL=you@your-university.edu              # leave blank for localhost

SECRET_KEY=<paste the generated value>
POSTGRES_PASSWORD=<paste the generated value>
DATABASE_URL=postgresql+psycopg2://autograde:<POSTGRES_PASSWORD>@db:5432/autograde
CORS_ORIGINS=https://autograde.your-university.edu

LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Then lock the file down so only you can read it:

```bash
chmod 600 .env          # macOS / Linux
```

> **AutoGrade refuses to start in production** if `SECRET_KEY` is still the
> default or a placeholder, if `DATABASE_URL` points at SQLite, or if the
> selected AI provider has no key. That is deliberate — a refused start is
> better than a silently insecure one. The error tells you exactly which
> value to fix.

---

## 3. Start, stop, restart

All commands run from the `autograde` folder.

```bash
# START (first time, or after changing code — builds the images)
docker compose -f docker-compose.prod.yml up -d --build

# START (normal, images already built)
docker compose -f docker-compose.prod.yml up -d

# STOP (keeps all data)
docker compose -f docker-compose.prod.yml stop

# RESTART everything
docker compose -f docker-compose.prod.yml restart

# RESTART just one service
docker compose -f docker-compose.prod.yml restart worker

# SHUT DOWN and remove containers (data volumes are kept)
docker compose -f docker-compose.prod.yml down

# See what is running
docker compose -f docker-compose.prod.yml ps
```

`-d` means "in the background". You can close the terminal afterwards.

> **Never run `down -v`.** The `-v` deletes the volumes — your entire
> gradebook and every uploaded submission. There is no undo except a
> backup.

Everything restarts automatically after a reboot (`restart:
unless-stopped`), as long as Docker itself starts on boot.

---

## 4. Migrations

**You do not run these by hand.** The API container runs
`alembic upgrade head` every time it starts, so a fresh install and an
upgrade both migrate themselves. Running it twice is harmless.

To confirm which migration is applied:

```bash
docker compose -f docker-compose.prod.yml exec db \
  psql -U autograde -d autograde -c "SELECT version_num FROM alembic_version;"
```

To run one manually (rarely needed):

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

---

## 5. Logs and health

```bash
# Follow everything (Ctrl+C to stop watching — it does not stop the app)
docker compose -f docker-compose.prod.yml logs -f

# One service
docker compose -f docker-compose.prod.yml logs -f worker

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail 100 api
```

Production logs are one JSON object per line. Useful searches:

```bash
# Failed sign-ins
docker compose -f docker-compose.prod.yml logs api | grep auth.login_failed

# Grading job history
docker compose -f docker-compose.prod.yml logs worker | grep grading_job

# Anything that went wrong
docker compose -f docker-compose.prod.yml logs | grep '"level":"error"'
```

Passwords, API keys and student work are never logged. Email addresses in
auth events appear as a salted hash, so you can correlate repeated
failures without the address itself being written down.

### Health check

```bash
curl -k https://localhost/api/health
```

A healthy system returns HTTP 200 and:

```json
{"status":"ok","database_ok":true,"llm_configured":true,...}
```

`database_ok:false` returns HTTP 503 — the check really queries the
database, so it is a genuine readiness signal, not just "the process is
alive".

Quick all-green check:

```bash
docker compose -f docker-compose.prod.yml ps
```

`api`, `db` and `frontend` should say `healthy`; `worker`, `caddy` and
`backup` say `Up`. The worker has no healthcheck on purpose — it serves no
port; if it dies, Docker restarts it and any interrupted job is picked up
again automatically.

---

## 6. Backups and restore

Backups run automatically every 24 hours into a Docker volume.

```bash
# List backups
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups

# Did the last one work?
docker compose -f docker-compose.prod.yml logs backup | tail -5

# Take one right now
docker compose -f docker-compose.prod.yml exec backup \
  pg_dump -h db -U autograde -d autograde -Fc -f /backups/manual-$(date +%F).dump
```

### Copy them off the machine

A backup on the same disk as the database is not a backup. Add this to the
host's crontab (`crontab -e`):

```cron
30 3 * * * docker run --rm -v autograde_backups:/b -v /srv/offsite:/out alpine cp -u /b/. /out/ -r
```

Student files live outside the database, so copy those too:

```bash
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/out \
  alpine tar czf /out/uploads-$(date +%F).tar.gz -C /u .
```

### Restore — practise this once before term starts

```bash
# 1. Stop everything that writes
docker compose -f docker-compose.prod.yml stop api worker frontend

# 2. Choose a dump
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups

# 3. Restore it
docker compose -f docker-compose.prod.yml exec backup \
  pg_restore -h db -U autograde -d autograde --clean --if-exists \
             /backups/autograde-<TIMESTAMP>.dump

# 4. Restore uploaded files if they were lost too
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/in \
  alpine tar xzf /in/uploads-<DATE>.tar.gz -C /u

# 5. Start again and verify
docker compose -f docker-compose.prod.yml start api worker frontend
curl -k https://localhost/api/health
```

Grading jobs that were mid-run when the dump was taken resume by
themselves within a minute; already-graded submissions are skipped, so you
do not pay the model twice.

---

## 7. Updating

```bash
cd autograde

# 1. Back up first — this is your rollback
docker compose -f docker-compose.prod.yml exec backup \
  pg_dump -h db -U autograde -d autograde -Fc -f /backups/pre-upgrade-$(date +%F).dump

# 2. Get the new version
git fetch --tags
git checkout v0.9.1-pilot

# 3. Rebuild and restart (migrations run automatically)
docker compose -f docker-compose.prod.yml up -d --build

# 4. Check
docker compose -f docker-compose.prod.yml ps
curl -k https://localhost/api/health
```

**Rollback:**

```bash
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml up -d --build
```

If the newer version applied a migration the older code cannot read, also
restore the pre-upgrade dump (§6). The dump is the rollback mechanism —
Alembic downgrades are not relied on.

---

## 8. Sharing it with colleagues

**This is the easy part.** Your colleagues install nothing. No Python, no
Docker, no API key. They open a link in a browser and sign in.

You send each of them three things:

```
URL:      https://autograde.your-university.edu
Email:    their.name@your-university.edu
Password: (the one you set for them)
```

### How to give them an account

Registration is open, so **anyone who can reach the URL can create an
account**. Two ways to handle that:

**Option A — you create the accounts (recommended for a pilot).**
Do this before you share the link:

```bash
curl -k -X POST https://localhost/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"colleague@university.edu","name":"Dr Colleague",
       "password":"a-long-password-you-generate","role":"professor"}'
```

Send them that email and password, and ask them to change it. (There is no
self-service password change yet — see "Remaining gaps" below.)

**Option B — they register themselves.** Send the link and tell them to
choose "Create account". Simpler, but anyone with the link can sign up, so
only do this on a university-internal network.

### What each colleague sees

* Only their own courses, assignments, submissions, grades and jobs.
  Isolation is enforced on every endpoint and verified by tests — one
  professor cannot see, grade, export or cancel another's work.
* By default they grade with **your** configured AI account, so they need
  no key of their own. If you would rather they paid for their own usage,
  they add a key under **Settings → AI providers** (§9).

### Making the URL reachable

| Situation | What to do |
|---|---|
| Everyone is on the campus network | Give AutoGrade a DNS name that resolves internally. Nothing else needed. |
| Colleagues work from home | Ask IT to publish the hostname, or require the university VPN (simplest and safest) |
| Just trying it out | Run it on your own machine and share `https://<your-ip>` on the same network |

Set `PUBLIC_HOSTNAME` to the real name and Caddy fetches a trusted HTTPS
certificate automatically. With `localhost` the certificate is
self-signed, so browsers show a warning — fine for testing, not for
sharing.

---

## 9. AI providers — three ways to grade

Grading needs a model. There are three configurations, and they can be
mixed: the server has a default, and any professor may override it for
themselves.

### 9.1 Administrator default (simplest — start here)

You put one key in `.env`; everyone uses it; you pay one bill.

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_GRADING_MODEL=gpt-4o
```

or Claude:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Restart afterwards: `docker compose -f docker-compose.prod.yml up -d`.

Colleagues do nothing. The sidebar shows *"Ready to grade — using the
OpenAI API"*.

### 9.2 Professor brings their own key (BYOK)

Any professor can go to **Settings → AI providers** and:

1. Pick a provider (OpenAI, Claude, or a local model).
2. Paste their API key and press **Save**.
3. Press **Test this key** — one small live call, so a bad key is found
   now rather than halfway through a batch of 200.
4. Choose **Grade using → My own … key**, then **Switch**.

Properties worth knowing:

* Keys are **encrypted at rest** (Fernet/AES) before they touch the
  database.
* After saving, a key is only ever shown as `****1234`. There is no
  "reveal" — a forgotten key is replaced, not recovered.
* Keys are **never returned by the API and never written to logs**.
* Keys are **strictly per-professor**. Another account cannot read, test
  or delete them.
* **Saving a key does not switch grading to it.** That is a separate
  click, so pasting a key can never silently redirect a course's spend.
* Remove a key and that professor falls back to your shared account.

> ⚠️ **If you change `SECRET_KEY`, every saved professor key becomes
> undecryptable** and each professor must re-enter theirs. To avoid that,
> set `CREDENTIAL_ENCRYPTION_KEY` to its own value now and never change it.

### 9.3 Local Qwen via Ollama (no per-token cost)

Detected on this machine: Ollama is running with **`qwen2.5-coder:7b`** and
**`qwen2.5:3b`** already pulled.

Server-wide, in `.env`:

```bash
LLM_PROVIDER=local
LOCAL_BASE_URL=http://host.docker.internal:11434/v1
LOCAL_MODEL=qwen2.5-coder:7b
LOCAL_API_KEY=not-needed
```

Or per professor, in Settings → AI providers → *Local model*, with
**Check this server** listing the models AutoGrade can actually see.

**Getting the URL right is the whole trick:**

| Where Ollama runs | `LOCAL_BASE_URL` |
|---|---|
| Same machine as Docker | `http://host.docker.internal:11434/v1` |
| Same machine, AutoGrade **not** in Docker | `http://localhost:11434/v1` |
| A different server | `http://that-server:11434/v1` |

Inside a container, `localhost` means *the container itself*, which is why
`host.docker.internal` exists. On Linux hosts you may need to add this to
the `api` and `worker` services in `docker-compose.prod.yml`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

For Ollama on another machine to accept connections, start it with
`OLLAMA_HOST=0.0.0.0:11434` and allow the port in the firewall. **Ollama
has no authentication**, so only expose it on a trusted network — never
straight to the internet.

#### ⚠️ The thing that surprises everyone

> **A colleague using your hosted AutoGrade cannot use Qwen installed on
> their own laptop.**

AutoGrade grades on the **server**. When it calls a model it does so from
the server, not from the browser. If a colleague sets
`http://localhost:11434/v1`, the server tries to reach *its own*
localhost — not their PC — and grading fails with "could not reach the
server". Their laptop is behind NAT and firewalls; the server has no route
to it, and punching one open would be a poor idea anyway.

**The simplest architecture for shared Qwen use** — recommended:

```
   professors' browsers
            │  HTTPS
            ▼
  ┌───────────────────────┐        ┌────────────────────────┐
  │  AutoGrade server     │ ─────► │  One shared Ollama      │
  │  (api + worker)       │  LAN   │  host on the same LAN   │
  └───────────────────────┘        │  qwen2.5-coder:7b       │
                                   └────────────────────────┘
```

One Ollama instance, on the same network as AutoGrade — the AutoGrade host
itself if it has the RAM, otherwise a GPU box nearby. Everyone shares it;
nobody installs anything. Set `LOCAL_BASE_URL` to that host once and it
works for every professor.

Sizing: a 7B model needs roughly 8 GB of RAM and grades noticeably slower
than a hosted API. `qwen2.5-coder:7b` is the better grader of the two you
have; `qwen2.5:3b` is faster but markedly more generous — in testing it
awarded full marks to a submission the larger models marked down. **Spot
check a handful of grades before trusting a small local model on real
coursework.**

The realistic options, in order of simplicity:

1. **Everyone uses your hosted key** (§9.1) — least effort, one bill.
2. **One shared Ollama on the LAN** — no per-token cost, keeps student
   work in-house.
3. **Each professor brings their own hosted key** (§9.2) — costs land on
   whoever incurs them.

Local Qwen on individual laptops only works if each professor runs
AutoGrade on their own machine, which is exactly the outcome this
deployment exists to avoid.

---

## 10. Changing the ports

If 80/443 are taken (Apache/XAMPP on this machine, for instance), create
`docker-compose.override.yml` next to the other compose files:

```yaml
services:
  caddy:
    ports: !override
      - "8080:80"
      - "8443:443"
```

Compose picks up `docker-compose.override.yml` automatically, so the
commands in this guide do not change. AutoGrade is then at
`https://your-host:8443`.

---

## 11. When something is wrong

| Symptom | Check |
|---|---|
| `docker: command not found` | Docker Desktop is not installed or not running |
| API keeps restarting | `logs api` — usually a `.env` value it refuses to start on |
| "Refusing to start in environment 'production'" | Read the list it prints; fix those values in `.env` |
| Grading stays "queued" forever | The worker is not running: `ps`, then `logs worker` |
| Every submission fails "could not reach the … server" | The worker cannot reach the provider. Check the key, and for Ollama check `LOCAL_BASE_URL` (§9.3) |
| Browser warns about the certificate | `PUBLIC_HOSTNAME=localhost` uses a self-signed cert. Use a real DNS name. |
| Port already in use | Something else owns 80/443 — see §10 |
| Sign-in returns 429 | Login throttling: 8 failures per account in 15 minutes. Wait, or `logs api \| grep auth.throttled` |

Collect this before asking for help:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail 50 api worker
curl -k https://localhost/api/health
```

---

## 12. Remaining gaps

Honest list of what is not there yet:

* **No self-service password change or reset.** You set passwords and
  distribute them; a forgotten password needs an administrator.
* **Registration is open.** Anyone who can reach the URL can create an
  account. Keep it on an internal network, or create the accounts
  yourself.
* **Sessions cannot be revoked** before their 8-hour expiry.
* **Single host.** No redundancy — if the machine is down, AutoGrade is
  down. Backups protect the data, not the uptime.
* **Prompt injection is mitigated, not solved.** A submission that tries
  to instruct the grader is flagged `prompt_injection` for review. Keep
  approving grades yourself; that is the real control.
* **Small local models are lenient.** Spot-check before trusting them.
* **Uploads live on one machine's disk.** Fine for one server; object
  storage would be needed to run two.
