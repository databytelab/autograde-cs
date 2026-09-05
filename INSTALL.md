# Installing AutoGrade

**Complete instructions for someone who has never used Docker.**

You will install one program (Docker), download AutoGrade, and run one
command. Budget **30 minutes**, most of which is downloading.

When you are finished, AutoGrade runs on your own machine or your own
server. Your students' work stays there. Nobody else — including whoever
gave you this package — can see it.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Install Docker](#2-install-docker)
3. [Download AutoGrade](#3-download-autograde)
4. [Run the setup script](#4-run-the-setup-script)
5. [Create your account](#5-create-your-account)
6. [Add your colleagues](#6-add-your-colleagues)
7. [Connect Canvas](#7-connect-canvas-optional)
8. [Using a local model instead of a paid API](#8-using-a-local-model-instead-of-a-paid-api)
9. [Everyday commands](#9-everyday-commands)
10. [If something goes wrong](#10-if-something-goes-wrong)

---

## 1. What you need

| | Detail |
|---|---|
| **A computer that stays on** | Windows 10/11, macOS, or Linux. A laptop is fine to trial; a machine that stays on is better for a department. |
| **Disk space** | About 10 GB |
| **Memory** | 4 GB free (8 GB if you will run a local AI model) |
| **An AI account** | An OpenAI **or** Anthropic API key — **or** Ollama for a free local model (§8) |
| **Administrator rights** | Only to install Docker, once |

You do **not** need Python, a database, or any web-server knowledge.

### About the AI key

AutoGrade needs a model to do the grading. Cheapest to start:

- **OpenAI** — <https://platform.openai.com/api-keys> → *Create new secret
  key*. Add about $10 of credit. A class of 30 costs well under a dollar.
- **Anthropic (Claude)** — <https://console.anthropic.com/settings/keys>
- **Free, private, no account** — install Ollama and use a local model
  (§8). Slower, and small models mark generously, but nothing leaves your
  machine.

Have the key ready before you start. **Copy it somewhere safe** — both
sites show it only once.

---

## 2. Install Docker

Docker runs AutoGrade's parts (web page, database, grader) without you
installing them one by one.

### Windows

1. Go to <https://www.docker.com/products/docker-desktop/>
2. Click **Download for Windows**.
3. Run the downloaded `Docker Desktop Installer.exe`.
4. Leave every option ticked (including WSL 2). Click **OK**.
5. **Restart your computer** when it asks. This is not optional.
6. After restarting, open **Docker Desktop** from the Start menu.
7. Accept the agreement. If it offers to sign in, click **Skip** — you do
   not need an account.
8. Wait until the whale icon in the bottom-left is **steady, not
   animating**. That means Docker is ready.

### macOS

1. Go to <https://www.docker.com/products/docker-desktop/>
2. Click **Download for Mac**, choosing **Apple chip** or **Intel chip** to
   match your Mac (Apple menu → About This Mac).
3. Open the downloaded `.dmg` and drag **Docker** into **Applications**.
4. Open Docker from Applications. Approve the permission prompt.
5. Wait for the whale icon in the menu bar to stop animating.

### Linux (Ubuntu/Debian)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Then **log out and back in** so the group change applies.

### Check it worked

Open a terminal — **Windows:** press Start, type `powershell`, press Enter.
**macOS:** press ⌘+Space, type `terminal`, press Enter — and run:

```bash
docker --version
```

You should see something like `Docker version 27.x.x`. If you get "command
not found", Docker did not install correctly, or you did not restart.

---

## 3. Download AutoGrade

**Option A — a ZIP file** (if that is what you were given)

1. Save the ZIP somewhere sensible, e.g. `Documents`.
2. Right-click → **Extract All** (Windows) or double-click (macOS).
3. You now have a folder called `autograde` or similar.

**Option B — from Git**

```bash
git clone <the repository address you were given> autograde
```

### Open a terminal *in that folder*

This trips people up more than anything else. The commands below only work
from inside the AutoGrade folder.

- **Windows:** open the folder in File Explorer, click the address bar,
  type `powershell`, press Enter.
- **macOS:** right-click the folder → **Services** → **New Terminal at
  Folder**.
- **Any system:** `cd` to it, e.g. `cd Documents/autograde`

Check you are in the right place:

```bash
ls        # macOS/Linux
dir       # Windows
```

You should see `docker-compose.prod.yml`, `setup.sh`, `setup.ps1`,
`README.md`.

---

## 4. Run the setup script

This generates your passwords and security keys, writes the configuration
file, and starts everything.

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

> If Windows says *"running scripts is disabled on this system"*, run this
> once, then try again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

**macOS / Linux:**

```bash
chmod +x setup.sh
./setup.sh
```

### What it asks

**"Web address people will use [localhost]"**
- Trying it on your own machine → press **Enter** for `localhost`.
- A server your colleagues will reach → type the DNS name, e.g.
  `autograde.your-university.edu`. It must already point at this machine.

**"Email for certificate expiry warnings"** *(only for a real address)*
Your email. It is where the free HTTPS certificate service sends renewal
warnings.

**"Which AI should grade?"**
`1` OpenAI, `2` Claude, `3` local Ollama model. Then paste your key — **it
will not appear as you type. That is normal.** Paste and press Enter.

Then it builds. **The first run takes 5–10 minutes** and prints a lot.
That is normal. It is downloading the database, the web server and Python.

When it finishes you will see:

```
OK  AutoGrade is running.

  Open:  https://localhost
```

---

## 5. Create your account

1. Open the address it printed in your browser.

2. **If you used `localhost`, the browser will warn you the site is not
   secure.** This is expected — the certificate is self-signed because
   `localhost` is not a real public name. Click **Advanced** →
   **Proceed to localhost**. On a real DNS name you get a proper
   certificate and no warning.

3. You will see the AutoGrade home page. Click **Create account**.

4. Fill in your name, email and a password. **Write the password down.**

5. Click **Create account**.

> **⚠️ Do this before anyone else can reach the address.**
> **The first account created becomes the administrator** — it is the only
> account that can create other accounts and reset passwords. After that,
> self sign-up is switched off, so nobody can create an account for
> themselves.

You are now signed in. Follow **`USER_GUIDE.md`** for how to actually
grade something.

---

## 6. Add your colleagues

Everyone else gets an account from you. They install nothing.

1. In the left sidebar, click **Account**.
2. Scroll to **Add someone**.
3. Enter their **Full name** and **Email**.
4. A random **Initial password** is filled in for you. Copy it.
5. Choose **professor** (can approve grades) or **ta** (can grade and
   comment, cannot approve).
6. Click **Create account**.

Send them three things:

```
Web address: https://autograde.your-university.edu
Email:       their.email@university.edu
Password:    the initial password you copied
```

Ask them to change it under **Account → Change your password**.

If someone forgets their password, open **Account**, expand their name, and
use **Reset their password**.

---

## 7. Connect Canvas (optional)

Skip this if you only want CSV/Excel/PDF exports.

**Canvas is connected per person**, because a Canvas token acts as *you* —
your token cannot write grades into a colleague's course, and theirs cannot
write into yours. So each instructor connects their own.

1. In the sidebar, click **Canvas**.
2. Expand **How do I get an access token?** and follow it:
   - In Canvas: **Account → Settings → + New Access Token**
   - Purpose: `AutoGrade`, then **Generate Token**
   - **Copy it immediately** — Canvas shows it once.
3. Back in AutoGrade, paste your **Canvas URL**
   (e.g. `https://canvas.your-university.edu`) and the **token**.
4. Click **Save**, then **Test connection**. It should say
   *"Connected … as <your name>"*.

Your token is encrypted before storage and shown afterwards only as
`****1234`. No one else on the instance can see or use it.

---

## 8. Using a local model instead of a paid API

Runs the AI on your own hardware. No per-use cost, and **nothing leaves
your machine**.

### Install Ollama

1. Download from <https://ollama.com/download> and install it.
2. Open a terminal and pull a model:

```bash
ollama pull qwen2.5-coder:7b
```

That is about 4.7 GB. `qwen2.5-coder:7b` is a good grader for code.
`qwen2.5:3b` is smaller and faster but marks noticeably more generously.

### Point AutoGrade at it

In the sidebar → **AI providers** → expand **Local model**:

1. **Ollama base URL** — this is the part people get wrong:

   | Where Ollama runs | What to type |
   |---|---|
   | Same machine as AutoGrade | `http://host.docker.internal:11434/v1` |
   | Another server | `http://that-server:11434/v1` |

   AutoGrade runs inside Docker, where `localhost` means *inside the
   container* — not your machine. `host.docker.internal` is how a
   container reaches the computer it runs on.

2. Click **Check this server**. It lists the models it can actually see.
   If it lists yours, the address is right.
3. Set **Model** to `qwen2.5-coder:7b`, click **Save**.
4. Click **Test this key**.
5. Scroll up, choose **My own Local model**, click **Switch**.

> **Important:** a colleague using *your* AutoGrade cannot use Ollama on
> *their* laptop. Grading happens on the server, so it can only reach a
> model the server can reach. For a shared instance, run one Ollama on the
> same network. See `CHOOSING_YOUR_SETUP.md` §9.3.

**Spot-check local grades.** Small models are more lenient than hosted
ones. Compare a few against your own marking before trusting a batch.

---

## 9. Everyday commands

Run these from the AutoGrade folder.

```bash
# Start (after a reboot, or if you stopped it)
docker compose -f docker-compose.prod.yml up -d

# Stop (keeps all your data)
docker compose -f docker-compose.prod.yml stop

# Restart
docker compose -f docker-compose.prod.yml restart

# Is it running?
docker compose -f docker-compose.prod.yml ps

# Watch what it is doing (Ctrl+C to stop watching)
docker compose -f docker-compose.prod.yml logs -f
```

> **Never add `-v`** to `down`. `docker compose ... down -v` deletes your
> entire gradebook and every uploaded file. There is no undo except a
> backup.

AutoGrade restarts by itself when the computer reboots, provided Docker
Desktop is set to start on login (it is, by default).

**Backups run automatically every night.** See `RUN_AND_SHARE.md` §6 for
how to copy them somewhere safe and how to restore — please do the restore
drill once before you rely on this.

---

## 10. If something goes wrong

| What you see | What to do |
|---|---|
| `docker: command not found` | Docker is not installed, or you did not restart after installing |
| `Cannot connect to the Docker daemon` | Docker Desktop is not running. Open it and wait for the whale to settle. |
| `running scripts is disabled` (Windows) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry |
| `port is already allocated` | Something else uses ports 80/443 (XAMPP, IIS, Skype). Stop it, or see `RUN_AND_SHARE.md` §10 |
| Browser: "not secure" | Expected on `localhost`. Advanced → Proceed. Use a real DNS name to avoid it. |
| "Refusing to start in environment 'production'" | A value in `.env` is missing or still a placeholder. The message names it. |
| Grading stays "queued" | The worker is not running: `docker compose -f docker-compose.prod.yml ps`, then `logs worker` |
| Every submission fails "could not reach the … server" | Wrong API key, no internet, or (for Ollama) the wrong URL — see §8 |
| Cannot sign in, 429 error | Too many wrong passwords. Wait 15 minutes. |
| Forgot the administrator password | The only account that can reset it is itself. Contact your supplier — recovery needs database access. |

### Starting completely over

This **deletes everything** — all courses, grades and submissions:

```bash
docker compose -f docker-compose.prod.yml down -v
rm .env          # del .env on Windows
./setup.sh       # or .\setup.ps1
```

### Getting help

Send these three outputs — they contain no passwords or student work:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail 50 api worker
docker --version
```

---

## What next

- **`USER_GUIDE.md`** — how to actually grade, click by click.
- **`CHOOSING_YOUR_SETUP.md`** — where student data lives and who can read
  it. Read before sharing with colleagues.
- **`RUN_AND_SHARE.md`** — backups, restore, upgrades, day-to-day running.
