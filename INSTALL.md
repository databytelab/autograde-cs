# Install AutoGrade

**Time needed:** about 30 minutes, most of it waiting for a download.
**You need:** a Windows computer, and about 10 GB of free disk space.

You install one program (Docker Desktop), then double-click one file. That is the whole installation. You will not edit any settings files, type any commands, or need to understand what is running.

---

## Step 1 — Install Docker Desktop

Docker is the program that runs AutoGrade. You install it once and never think about it again.

1. Go to **<https://docs.docker.com/get-docker/>**
2. Click **Docker Desktop for Windows**
3. Open the file you downloaded (`Docker Desktop Installer.exe`)
4. Click **OK** to every question. If it asks about **WSL 2**, say yes
5. When it finishes, **restart your computer**
6. After restarting, open **Docker Desktop** from the Start menu
7. Accept the licence terms. If it offers to sign in, click **Skip** — you do not need an account
8. Wait until the whale icon at the bottom-right of your screen stops moving

**Expected result:** the Docker Desktop window says *Engine running* at the bottom-left.

> Docker Desktop must be running for AutoGrade to work. It starts by itself when you turn your computer on.

---

## Step 2 — Put AutoGrade somewhere sensible

1. Find the AutoGrade ZIP file you were given
2. Right-click it → **Extract All…**
3. Choose a folder you will not accidentally delete — `Documents` is a good choice, the Desktop is fine too
4. Click **Extract**

**Expected result:** a folder named something like `autograde-v0.9.3` containing files including **Start AutoGrade**.

> Do not move this folder after you start using AutoGrade. Your courses and grades live inside it.

---

## Step 3 — Start AutoGrade

1. Open the AutoGrade folder
2. Double-click **`Start AutoGrade`**

A black window opens and prints text. **The first time, this takes 5 to 10 minutes** — it is downloading and building everything AutoGrade needs. You only wait this long once; later starts take about twenty seconds.

**Expected result:** the window ends with

```
  OK   Database, grading worker and interface are all running

AutoGrade is ready
  Opening http://localhost:8501 in your browser.
```

and your web browser opens AutoGrade by itself.

> **If Windows shows a security warning** ("Windows protected your PC"), click **More info** → **Run anyway**. This appears because the file was downloaded, not because anything is wrong.

> **If the window says Docker is not running**, it will try to start Docker Desktop for you. Wait — it can take a minute. If it gives up, open Docker Desktop from the Start menu yourself and then double-click **Start AutoGrade** again.

---

## Step 4 — Create your account

The browser is showing the AutoGrade welcome page.

1. Click **Create account**
2. **Full name** — your name
3. **Email** — your university email
4. **Password** — choose one, and **write it down**
5. **Role** — leave it as `professor`
6. Click **Create account**

**Expected result:** you are signed in, and you see a sidebar on the left listing *Dashboard*, *New assignment*, *Upload & grade*, *Review results*, *Export*, and *Settings*.

> **The first account created is the administrator.** That is yours. Nobody else can create an account on your AutoGrade unless you create it for them.
>
> There is no "forgot password" email. If you lose this password, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Step 5 — Set up the AI

AutoGrade needs one AI account to read submissions and propose grades. Until you do this, everything else works but nothing can be graded.

1. In the sidebar, under **Settings**, click **AI providers**
2. Follow **[AI_PROVIDERS.md](AI_PROVIDERS.md)**, which walks through all three choices:
   - **OpenAI** — easiest, costs a few cents per class
   - **Claude** — same idea, different company
   - **Ollama** — free, runs on your own computer, needs 8 GB of memory

**Expected result:** the top of the AI providers page turns green and says *Grading is set up*.

---

## Step 6 — Grade something

You are finished installing. Open **[USER_GUIDE.md](USER_GUIDE.md)** and grade a handful of submissions from last term.

---

## Every day after this

| To do this | Double-click |
|---|---|
| Open AutoGrade | **Start AutoGrade** |
| Close it down | **Stop AutoGrade** |
| Fix something odd | **Restart AutoGrade** |
| Save a copy of everything | **Backup AutoGrade** |
| Go back to a saved copy | **Restore AutoGrade** |
| Install a newer version | **Update AutoGrade** |

Full details in **[RUN_AND_SHARE.md](RUN_AND_SHARE.md)**.

You can leave AutoGrade running all the time. It uses very little while idle, and it starts again by itself when you turn your computer on.

---

## Where your data is

Everything stays on your computer:

- **Your courses, rubrics and grades** — in a database inside Docker on this machine
- **Student files you upload** — the same
- **Your API key and Canvas token** — encrypted, on this machine
- **Backups** — in the `backups` folder inside the AutoGrade folder

The one thing that leaves your computer is the **text of each submission**, sent to whichever AI provider you chose so that it can be graded. OpenAI and Anthropic both state that data sent through their APIs is not used to train their models. If you would rather nothing at all left your computer, use **Ollama** — see [AI_PROVIDERS.md](AI_PROVIDERS.md).

Nobody who gave you this package can see any of it.

---

## If something went wrong

Every common problem and its fix is in **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

---

## Installing on a Mac or on Linux

The same steps work, with two differences:

- In step 1, choose **Docker Desktop for Mac** (Apple chip or Intel chip) or install Docker Engine on Linux
- In step 3, instead of double-clicking `Start AutoGrade`, open a terminal in the AutoGrade folder and run:

```bash
./autograde.sh start
```

Everything after that is identical. `./autograde.sh stop`, `restart`, `update`, `backup` and `restore` match the Windows buttons.
