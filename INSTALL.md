# Install AutoGrade

Two ways to run it. Pick one.

| | **Option A — Docker** | **Option B — Without Docker** |
|---|---|---|
| Install first | Docker Desktop | Python 3.11 |
| Terminals to keep open | 0 | 3 |
| Database | PostgreSQL | SQLite file |
| Backups | Automatic, nightly | None |
| Other people can use it | Yes | No |
| Use it for | A real installation | Trying it on your own machine |

**Option A is the one to install for real use.**

---

# Option A — Docker

## A1. Install Docker

### Windows

1. Go to <https://docs.docker.com/get-docker/>
2. Click **Docker Desktop for Windows**
3. Run the downloaded installer
4. Keep every default. Click **OK** when it asks about WSL 2
5. Restart your computer
6. Open **Docker Desktop** from the Start menu
7. Wait until the whale icon in the taskbar stops animating

### macOS

1. Go to <https://docs.docker.com/get-docker/>
2. Click **Docker Desktop for Mac**. Choose **Apple chip** or **Intel chip**
3. Open the downloaded `.dmg` and drag Docker to **Applications**
4. Open **Docker** from Applications
5. Wait until the whale icon in the menu bar stops animating

### Linux (Ubuntu / Debian)

```bash
curl -fsSL https://get.docker.com | sudo sh
```

```bash
sudo usermod -aG docker $USER
```

Log out and log back in.

## A2. Check Docker works

```bash
docker --version
```

```bash
docker compose version
```

Both must print a version number. If either fails, go back to A1.

## A3. Get the AutoGrade folder

**If you were given a ZIP file:**

1. Save the ZIP to your Desktop
2. Right-click it → **Extract All** (Windows) or double-click it (macOS)
3. You now have a folder called `autograde-<version>`

**If you were given a repository address:**

```bash
git clone <the address you were given> autograde
```

## A4. Open a terminal inside that folder

- **Windows** — open the folder in File Explorer, click the address bar, type `powershell`, press Enter
- **macOS** — right-click the folder → **Services** → **New Terminal at Folder**
- **Linux** — right-click inside the folder → **Open in Terminal**

Check you are in the right place:

```bash
ls
```

You should see `docker-compose.prod.yml`, `setup.sh`, `setup.ps1` and `README.md`.

## A5. Change the ports (only if 80 or 443 are taken)

Skip this step unless you already run Apache, IIS, XAMPP or Skype.

Create a file called `docker-compose.override.yml` in the same folder, containing exactly:

```yaml
services:
  caddy:
    ports: !override
      - "8081:80"
      - "8444:443"
```

Your web address then becomes `https://localhost:8444` instead of `https://localhost` everywhere below.

## A6. Run the installer

**Windows:**

```bash
.\setup.ps1
```

If Windows says *running scripts is disabled on this system*, run this once and then repeat:

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**macOS / Linux:**

```bash
chmod +x setup.sh
```

```bash
./setup.sh
```

## A7. Answer its questions

| It asks | Type this |
|---|---|
| Web address people will use | Press **Enter** for `localhost`, or type your server's DNS name |
| Email for certificate warnings | Your email (only asked if you typed a DNS name) |
| Which AI should grade? | `1` OpenAI, `2` Claude, `3` local Ollama |
| Paste your API key | Paste it and press Enter. **Nothing appears on screen. That is normal.** |

Then it builds. **The first run takes 5–10 minutes** and prints a lot of text.

It finishes with:

```
OK  AutoGrade is running.

  Open:  https://localhost
```

## A8. Open AutoGrade

Go to the address it printed.

If you used `localhost`, the browser says the site is not secure. Click **Advanced** → **Proceed to localhost (unsafe)**. On a real DNS name there is no warning.

## A9. Create your account

**Do this before anyone else can reach the address. The first account becomes the administrator.**

1. Click **Create account**
2. Type your **name**
3. Type your **email**
4. Type a **password**, and write it down
5. Click **Create account**

You are signed in. Self sign-up is now closed — nobody else can create their own account.

Now go to **[USER_GUIDE.md](USER_GUIDE.md)**.

## A10. Everyday commands

Run these from the AutoGrade folder.

Start it (after a reboot, or after stopping it):

```bash
docker compose -f docker-compose.prod.yml up -d
```

Stop it (keeps all data):

```bash
docker compose -f docker-compose.prod.yml stop
```

See what is running:

```bash
docker compose -f docker-compose.prod.yml ps
```

Watch what it is doing (`Ctrl+C` stops watching, not the app):

```bash
docker compose -f docker-compose.prod.yml logs -f
```

**Never add `-v` to `down`.** `down -v` deletes every course, grade and uploaded file.

---

# Option B — Without Docker

For trying AutoGrade on your own machine. Not for sharing with anyone.

## B1. Install Python 3.11

1. Go to <https://www.python.org/downloads/>
2. Download **Python 3.11**
3. Run the installer. On Windows, tick **Add python.exe to PATH**

```bash
python --version
```

## B2. Open a terminal in the AutoGrade folder

See step A4.

## B3. Create the environment

```bash
python -m venv venv
```

**Windows:**

```bash
venv\Scripts\activate
```

**macOS / Linux:**

```bash
source venv/bin/activate
```

```bash
pip install -r requirements.txt
```

## B4. Write the settings file

**Windows:**

```bash
copy .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Open `.env` in Notepad or any text editor and set these three lines:

```ini
ENVIRONMENT=development
LLM_PROVIDER=openai
OPENAI_API_KEY=paste-your-key-here
```

Save and close.

## B5. Create the database

```bash
alembic upgrade head
```

## B6. Start three terminals

All three stay open. All three in the AutoGrade folder, with `venv` activated.

**Terminal 1 — the API:**

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Wait for `Application startup complete`.

**Terminal 2 — the grading worker:**

```bash
python -m backend.worker
```

It prints nothing until you grade something. That is correct. **Without this terminal, grading stays stuck on "queued".**

**Terminal 3 — the interface:**

```bash
python -m streamlit run frontend_streamlit/app.py
```

## B7. Open AutoGrade

Go to **http://localhost:8501**

No certificate warning — there is no HTTPS in this mode.

## B8. Create your account

1. Click **Create account**
2. Type your name, email and a password
3. Click **Create account**

Now go to **[USER_GUIDE.md](USER_GUIDE.md)**.

## B9. Stopping and starting again

Stop: press `Ctrl+C` in each of the three terminals.

Start again: repeat step B6. Your data is still there.

## B10. Starting over with an empty database

**Windows:**

```bash
del autograde.db autograde.db-shm autograde.db-wal
```

**macOS / Linux:**

```bash
rm -f autograde.db autograde.db-shm autograde.db-wal
```

Then:

```bash
alembic upgrade head
```

---

# If something goes wrong

| What you see | What to do |
|---|---|
| `docker: command not found` | Docker is not installed, or you did not restart after installing. See A1. |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running. Open it and wait for the whale to settle. |
| `docker: unknown command: docker compose` | Type `docker-compose` (with a hyphen) instead of `docker compose` in every command. |
| `running scripts is disabled` (Windows) | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then try again. |
| `port is already allocated` | Something else uses ports 80/443. Do step A5. |
| Browser: *not secure* | Expected on `localhost`. Click **Advanced** → **Proceed**. |
| `Refusing to start in environment 'production'` | A value in `.env` is missing. The message names it. |
| Grading stays on **queued** | Option A: run `docker compose -f docker-compose.prod.yml logs worker`. Option B: you did not start Terminal 2. |
| `Cannot reach the backend` | Option B: Terminal 1 is not running. |
| Every submission fails *could not reach the server* | Wrong API key, or no internet. |
| `429` when signing in | Too many wrong passwords. Wait 15 minutes. |
| Forgot the administrator password | See **Recovering the administrator** below. |

## Recovering the administrator

Only an administrator can reset passwords. If you lose that account, change `choose-a-long-new-password` in the line below and run it on the machine AutoGrade is installed on:

```bash
docker compose -f docker-compose.prod.yml exec api python -c "from backend.database import SessionLocal; from backend.models.user import User; from backend.utils.auth_utils import hash_password; db=SessionLocal(); u=db.query(User).filter(User.is_admin==True).order_by(User.id).first(); u.password_hash=hash_password('choose-a-long-new-password'); db.commit(); print('Reset', u.email)"
```

On Option B, activate the venv and run the same thing without Docker:

```bash
python -c "from backend.database import SessionLocal; from backend.models.user import User; from backend.utils.auth_utils import hash_password; db=SessionLocal(); u=db.query(User).filter(User.is_admin==True).order_by(User.id).first(); u.password_hash=hash_password('choose-a-long-new-password'); db.commit(); print('Reset', u.email)"
```

Sign in with it, then change it under **Settings → Account**.

## Getting help

Send these three outputs. They contain no passwords and no student work.

```bash
docker compose -f docker-compose.prod.yml ps
```

```bash
docker compose -f docker-compose.prod.yml logs --tail 50 api worker
```

```bash
docker --version
```

---

# Next

- **[USER_GUIDE.md](USER_GUIDE.md)** — how to grade, click by click
- **[RUN_AND_SHARE.md](RUN_AND_SHARE.md)** — adding people, backups, upgrades
- **[CHOOSING_YOUR_SETUP.md](CHOOSING_YOUR_SETUP.md)** — where to run it, and who can read the data
