# Running AutoGrade

For the person who runs the server. Every command runs from the AutoGrade folder.

To install it in the first place, see **[INSTALL.md](INSTALL.md)**.

If you changed the ports (INSTALL.md step A5), replace `https://localhost` with `https://localhost:8444` throughout.

---

## Contents

1. [Start, stop, restart](#1-start-stop-restart)
2. [Check it is healthy](#2-check-it-is-healthy)
3. [Read the logs](#3-read-the-logs)
4. [Add and manage people](#4-add-and-manage-people)
5. [Choose which AI grades](#5-choose-which-ai-grades)
6. [Use a local model (Ollama)](#6-use-a-local-model-ollama)
7. [Back up](#7-back-up)
8. [Restore](#8-restore)
9. [Upgrade](#9-upgrade)
10. [Change the ports](#10-change-the-ports)
11. [Share it with colleagues](#11-share-it-with-colleagues)
12. [Send the package to another department](#12-send-the-package-to-another-department)
13. [Release checklist](#13-release-checklist)
14. [Invite the first professors](#14-invite-the-first-professors)
15. [Troubleshooting](#15-troubleshooting)
16. [Known limits](#16-known-limits)

---

## 1. Start, stop, restart

Start:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Start after changing code or settings:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Stop (keeps all data):

```bash
docker compose -f docker-compose.prod.yml stop
```

Restart everything:

```bash
docker compose -f docker-compose.prod.yml restart
```

Restart one service:

```bash
docker compose -f docker-compose.prod.yml restart worker
```

Remove the containers, keep the data:

```bash
docker compose -f docker-compose.prod.yml down
```

**Never run `down -v`.** It deletes your entire gradebook and every uploaded file.

AutoGrade starts again by itself after a reboot, as long as Docker starts on boot.

---

## 2. Check it is healthy

```bash
docker compose -f docker-compose.prod.yml ps
```

Expected:

| Service | State |
|---|---|
| `api` | healthy |
| `db` | healthy |
| `frontend` | healthy |
| `worker` | Up |
| `caddy` | Up |
| `backup` | Up |

`worker` has no health check because it serves no port.

```bash
curl -k https://localhost/api/health
```

Expected:

```json
{"status":"ok","database_ok":true,"llm_configured":true}
```

`database_ok:false` returns HTTP 503.

---

## 3. Read the logs

Everything, live (`Ctrl+C` stops watching, not the app):

```bash
docker compose -f docker-compose.prod.yml logs -f
```

One service:

```bash
docker compose -f docker-compose.prod.yml logs -f worker
```

Last 100 lines:

```bash
docker compose -f docker-compose.prod.yml logs --tail 100 api
```

Failed sign-ins:

```bash
docker compose -f docker-compose.prod.yml logs api | grep auth.login_failed
```

Grading job history:

```bash
docker compose -f docker-compose.prod.yml logs worker | grep grading_job
```

Anything that went wrong:

```bash
docker compose -f docker-compose.prod.yml logs | grep '"level":"error"'
```

Passwords, API keys and student work are never logged. Email addresses appear as a salted hash.

---

## 4. Add and manage people

Self sign-up is closed. You create every account after the first one.

### Add someone

1. Sign in as the administrator
2. Click **Account** under **Settings**
3. Scroll to **Add someone**
4. Type their **Full name** and **Email**
5. Copy the **Initial password** shown
6. Choose **professor** (can approve grades) or **ta** (cannot approve)
7. Click **Create account**

Send them three things:

```
Web address: https://autograde.your-university.edu
Email:       their.name@your-university.edu
Password:    the initial password you copied
```

Ask them to change it under **Settings → Account → Change your password**.

### Reset a forgotten password

1. Click **Account** under **Settings**
2. Under **People on this instance**, expand their name
3. Type a new password
4. Click **Reset password**

### Remove someone who has left

1. Click **Account** under **Settings**
2. Under **People on this instance**, expand their name
3. Click **Deactivate**

Their courses and grades stay. They can no longer sign in.

### Let people sign themselves up

Only on a network nobody outside the university can reach.

1. Open `.env`
2. Set `ALLOW_OPEN_REGISTRATION=true`
3. Save
4. Restart:

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 5. Choose which AI grades

### Option 1 — one key for everyone (start here)

1. Open `.env`
2. Set these lines for OpenAI:

   ```ini
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...
   OPENAI_GRADING_MODEL=gpt-4o
   ```

   or for Claude:

   ```ini
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Save
4. Restart:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Colleagues do nothing. The sidebar shows *Ready to grade — using the OpenAI API*.

### Option 2 — each professor uses their own key

Each of them does this themselves:

1. Click **AI providers** under **Settings**
2. Expand the provider they want
3. Paste the key into **API key**, click **Save**
4. Click **Test this key**
5. Scroll up to **Which account grades your submissions**
6. Choose **My own … key**, click **Switch**

Keys are encrypted before storage, shown afterwards only as `****1234`, never logged, and never visible to any other account.

**Set `CREDENTIAL_ENCRYPTION_KEY` in `.env` and never change it.** If you change `SECRET_KEY` without it, every saved key becomes unreadable and each professor must re-enter theirs.

---

## 6. Use a local model (Ollama)

No per-token cost. Slower than a hosted API.

### Install and pull a model

1. Install Ollama from <https://ollama.com/download>
2. Pull the model:

```bash
ollama pull qwen2.5-coder:7b
```

### Point AutoGrade at it

1. Open `.env`
2. Set:

   ```ini
   LLM_PROVIDER=local
   LOCAL_BASE_URL=http://host.docker.internal:11434/v1
   LOCAL_MODEL=qwen2.5-coder:7b
   LOCAL_API_KEY=not-needed
   ```

3. Save
4. Restart:

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Getting the URL right

| Where Ollama runs | `LOCAL_BASE_URL` |
|---|---|
| Same machine as Docker | `http://host.docker.internal:11434/v1` |
| Same machine, AutoGrade not in Docker | `http://localhost:11434/v1` |
| A different server | `http://that-server:11434/v1` |

On Linux hosts, add this to the `api` and `worker` services in `docker-compose.prod.yml`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

For Ollama on another machine, start it with `OLLAMA_HOST=0.0.0.0:11434` and open the port in the firewall. Ollama has no authentication — keep it on a trusted network only.

### What will not work

**A colleague using your server cannot use Ollama installed on their own laptop.** Grading runs on the server, so `http://localhost:11434/v1` points at the server, not at their PC.

If several people want a local model, run **one** Ollama on the same network as AutoGrade and point `LOCAL_BASE_URL` at it.

### Sizing

- A 7B model needs about 8 GB RAM
- `qwen2.5-coder:7b` grades better than `qwen2.5:3b`
- Small local models are lenient. Spot-check a handful of grades before trusting one

---

## 7. Back up

Backups run automatically every 24 hours into a Docker volume.

List them:

```bash
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups
```

Check the last one worked:

```bash
docker compose -f docker-compose.prod.yml logs backup | tail -5
```

Take one now:

```bash
docker compose -f docker-compose.prod.yml exec backup pg_dump -h db -U autograde -d autograde -Fc -f /backups/manual-$(date +%F).dump
```

### Copy them off the machine

A backup on the same disk is not a backup. Add to the host's crontab (`crontab -e`):

```cron
30 3 * * * docker run --rm -v autograde_backups:/b -v /srv/offsite:/out alpine cp -u /b/. /out/ -r
```

Student files live outside the database, so copy those too:

```bash
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/out alpine tar czf /out/uploads-$(date +%F).tar.gz -C /u .
```

---

## 8. Restore

Practise this once before term starts.

**1. Stop everything that writes:**

```bash
docker compose -f docker-compose.prod.yml stop api worker frontend
```

**2. Choose a dump:**

```bash
docker compose -f docker-compose.prod.yml exec backup ls -lh /backups
```

**3. Restore it** (replace `<TIMESTAMP>`):

```bash
docker compose -f docker-compose.prod.yml exec backup pg_restore -h db -U autograde -d autograde --clean --if-exists /backups/autograde-<TIMESTAMP>.dump
```

**4. Restore uploaded files if they were lost too** (replace `<DATE>`):

```bash
docker run --rm -v autograde_uploads:/u -v /srv/offsite:/in alpine tar xzf /in/uploads-<DATE>.tar.gz -C /u
```

**5. Start again:**

```bash
docker compose -f docker-compose.prod.yml start api worker frontend
```

**6. Verify:**

```bash
curl -k https://localhost/api/health
```

Jobs that were mid-run when the dump was taken resume within a minute. Already-graded submissions are skipped.

---

## 9. Upgrade

**1. Back up first — this is your rollback:**

```bash
docker compose -f docker-compose.prod.yml exec backup pg_dump -h db -U autograde -d autograde -Fc -f /backups/pre-upgrade-$(date +%F).dump
```

**2a. If you have a git checkout:**

```bash
git fetch --tags
```

```bash
git checkout v0.9.2-pilot
```

**2b. If you were given a ZIP:**

1. Unzip the new version next to the old folder
2. Copy `.env` from the old folder into the new one
3. Open a terminal in the new folder

**3. Rebuild (migrations run automatically):**

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**4. Check:**

```bash
docker compose -f docker-compose.prod.yml ps
```

```bash
curl -k https://localhost/api/health
```

### Rolling back

Go back to the previous tag or the old ZIP folder and run:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

If the newer version applied a migration the older code cannot read, restore the pre-upgrade dump as well (section 8).

---

## 10. Change the ports

If 80 or 443 are taken, create `docker-compose.override.yml` next to the other compose files:

```yaml
services:
  caddy:
    ports: !override
      - "8081:80"
      - "8444:443"
```

Compose picks it up automatically. AutoGrade is then at `https://your-host:8444`.

---

## 11. Share it with colleagues

They install nothing. They open a link and sign in.

**1. Make sure they can reach it:**

| Situation | What to do |
|---|---|
| Everyone is on the campus network | Give AutoGrade a DNS name that resolves internally |
| Colleagues work from home | Ask IT to publish the hostname, or require the university VPN |
| Just trying it out | Share `https://<your-ip>` on the same network |

Set `PUBLIC_HOSTNAME` in `.env` to the real name and restart. Caddy fetches a trusted certificate automatically. With `localhost` the certificate is self-signed and browsers warn.

**2. Create their account** — section 4.

**3. Send them the address, their email, their password, and [USER_GUIDE.md](USER_GUIDE.md).**

Each colleague sees only their own courses, assignments, submissions and grades.

---

## 12. Send the package to another department

They run AutoGrade on their own hardware, with their own AI key and their own Canvas token. Nothing of theirs reaches you.

**1. Tag the release:**

```bash
git tag -a v0.9.2-pilot -m "Installable bundle"
```

**2. Build the ZIP:**

```bash
python scripts/package_release.py
```

It writes `dist/autograde-<version>.zip` from committed files only, then refuses to ship if anything inside looks like a live API key or Canvas token.

**3. Send them:**

| | |
|---|---|
| `autograde-<version>.zip` | The software |
| One sentence | *Unzip it, open a terminal in the folder, and follow INSTALL.md* |

`INSTALL.md`, `USER_GUIDE.md` and this file are already inside the ZIP.

**4. Tell them what they need first:**

- A machine that stays on — a small VM or spare desktop
- Docker Desktop or Docker Engine
- Their own OpenAI or Anthropic key, or Ollama on the same machine
- A hostname, if colleagues will reach it from other machines

They do not need Python, PostgreSQL or a web server.

---

## 13. Release checklist

Tick every box before you send anyone a link.

**Server**

- [ ] Ports 80 and 443 are free, or the override in section 10 applied
- [ ] `setup.sh` / `setup.ps1` run, or `.env` filled in by hand
- [ ] `ENVIRONMENT=production`
- [ ] `SECRET_KEY` generated, 48+ random characters
- [ ] `CREDENTIAL_ENCRYPTION_KEY` set to its own value
- [ ] `POSTGRES_PASSWORD` generated and matching inside `DATABASE_URL`
- [ ] `DATABASE_URL` points at PostgreSQL, not SQLite
- [ ] `PUBLIC_HOSTNAME` is a real DNS name your colleagues can resolve
- [ ] `ACME_EMAIL` set
- [ ] `CORS_ORIGINS` is your public URL
- [ ] AI provider configured and working

**Start and verify**

- [ ] `docker compose -f docker-compose.prod.yml up -d --build`
- [ ] Six services running; `api`, `db`, `frontend` healthy
- [ ] `curl https://<host>/api/health` returns 200 and `database_ok: true`
- [ ] Sign-in page loads with a valid certificate
- [ ] You created your own account first, before sharing the URL
- [ ] Each colleague's account created under **Settings → Account**
- [ ] One full run: course → assignment → upload → grade → review → approve → export
- [ ] Grading still finishes after you close and reopen the browser
- [ ] A second test account cannot see your course — then deactivate it

**Operations**

- [ ] `logs backup` shows a successful dump
- [ ] Restore drill done at least once
- [ ] Off-host copy of `backups` and `uploads` scheduled
- [ ] Docker starts on boot

---

## 14. Invite the first professors

Aim for 3–5 colleagues, one course each, one real assignment, within a fortnight.

**Before you invite anyone:**

1. Finish section 13
2. Grade one of your own past assignments end to end
3. Decide who pays: your shared key, their own keys, or a shared Ollama

**The invitation:**

> Subject: **AutoGrade pilot — your login**
>
> Hi <name>,
>
> AutoGrade grades CS assignments against a rubric you write, and shows you
> every score for review before anything is final. It never publishes a
> grade on its own — you approve each one.
>
> Nothing to install. Open the link and sign in:
>
> URL: https://autograde.your-university.edu
> Email: <their email>
> Password: <their password>
>
> To try it, about 20 minutes:
> 1. **New assignment** — create a course and an assignment, and paste your
>    marking scheme. It turns that into a rubric you can edit.
> 2. **Upload & grade** — upload a handful of past submissions and press
>    Grade. It runs on the server, so you can close the tab.
> 3. **Review results** — read the feedback, change any score you disagree
>    with, then approve.
> 4. **Export** — CSV, Excel, or a per-student PDF.
>
> Two things I would like to hear:
> * Where the AI's score differed from yours, and by how much.
> * Anything in the interface you had to guess at.
>
> Please use last term's work rather than anything live while we pilot.
>
> — <you>

**During the pilot:**

- [ ] Watch spend over the first few batches
- [ ] Check in after each colleague's first real batch
- [ ] Keep a list of whatever they had to guess at
- [ ] Review anything flagged **Tried to instruct the grader** yourself

**Tell them plainly:**

- Grades are proposals until they approve them
- Submissions are sent to the configured AI provider — say which one
- Use last term's coursework during the pilot
- If they get locked out, you reset their password
- Data is backed up nightly — tell them the recovery window

---

## 15. Troubleshooting

| What you see | What to do |
|---|---|
| `port is already allocated` | Something else owns 80/443. See section 10. |
| `Refusing to start in environment 'production'` | A value in `.env` is missing. The message names it. |
| `api` never becomes healthy | `logs api`. Usually a wrong `DATABASE_URL` or `POSTGRES_PASSWORD`. |
| Grading stays on **queued** | `ps` — is `worker` up? Then `logs worker`. |
| Every submission fails *could not reach the server* | Wrong API key, or for Ollama a wrong `LOCAL_BASE_URL`. See section 6. |
| Certificate warning on a real hostname | DNS does not point here yet, or 80/443 are not reachable from outside. |
| `429` when signing in | Too many wrong passwords. Wait 15 minutes. |
| Someone forgot their password | Section 4. |
| You forgot the administrator password | See **Recovering the administrator** in INSTALL.md. |

---

## 16. Known limits

- **No reset-by-email.** People change their own password once signed in; a forgotten one needs the administrator.
- **Sessions cannot be revoked** before their 8-hour expiry.
- **Single host.** If the machine is down, AutoGrade is down.
- **Prompt injection is flagged, not solved.** Approving grades yourself is the control.
- **Small local models are lenient.** Spot-check before trusting them.
- **Uploads live on one machine's disk.**
