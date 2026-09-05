# When something goes wrong

Find your problem below. If it is not here, see [Getting help](#getting-help) at the bottom.

**The first thing to try, for almost anything:** double-click **`Restart AutoGrade`**. It is safe and loses nothing.

---

## Starting up

### The window flashes and disappears

Windows blocked the file because it came from a download.

1. Right-click **`Start AutoGrade`** → **Properties**
2. At the bottom, if there is an **Unblock** tick-box, tick it
3. Click **OK** and try again

### "Windows protected your PC"

Click **More info** → **Run anyway**. This appears for any file that was downloaded rather than installed.

### "Docker Desktop is not installed"

You skipped step 1 of [INSTALL.md](INSTALL.md), or Docker did not finish installing.

1. Install it from <https://docs.docker.com/get-docker/>
2. **Restart your computer** — this part is often missed
3. Open Docker Desktop once and wait for the whale icon to settle
4. Try **Start AutoGrade** again

### "Docker Desktop is installed but will not start"

1. Open **Docker Desktop** from the Start menu yourself
2. Wait until the bottom-left says **Engine running** — the first start after a reboot can take two minutes
3. Then double-click **Start AutoGrade**

If Docker Desktop itself will not start, restart the computer. If it still will not, reinstall Docker Desktop.

### "AutoGrade started but is not answering"

Usually it just needs longer, especially the first time.

1. Wait two minutes
2. Double-click **Start AutoGrade** again
3. If it happens again, double-click **Show AutoGrade Logs** and read the last twenty lines

### It has been building for more than 15 minutes

The first build downloads about 2 GB. On a slow connection this is normal. Leave it. If the window has printed nothing new for ten minutes, close it, check your internet, and start again — it continues from where it got to.

### "port is already allocated"

Something else on your computer is using the same door. AutoGrade normally moves out of the way by itself; if it could not:

1. Double-click **Stop AutoGrade**
2. Open `.env` in the AutoGrade folder with Notepad
3. Change `AUTOGRADE_PORT=8501` to `AUTOGRADE_PORT=8555`
4. Save, close, and double-click **Start AutoGrade**

---

## Signing in

### The browser did not open

Open it yourself and go to **<http://localhost:8501>**.

If the address bar shows a different port in the Start window, use that number instead.

### "This site can't be reached"

AutoGrade is not running. Double-click **Start AutoGrade** and wait for it to say it is ready.

### I forgot my password

There is no reset email — AutoGrade does not send email.

- **If you have a colleague's account on this AutoGrade with administrator rights**, ask them to reset it under **Settings → Account → People**.
- **If it is your own single-user installation**, you can reset it yourself. Open PowerShell in your AutoGrade folder, change `choose-a-new-password` below to what you want, and run it as one line:

```bash
docker compose -f docker-compose.local.yml exec api python -c "from backend.database import SessionLocal; from backend.models.user import User; from backend.utils.auth_utils import hash_password; db=SessionLocal(); u=db.query(User).filter(User.is_admin==True).order_by(User.id).first(); u.password_hash=hash_password('choose-a-new-password'); db.commit(); print('Reset', u.email)"
```

Then sign in with that and change it under **Settings → Account**.

### "Too many attempts" / error 429

You typed the wrong password several times. Wait 15 minutes and try again. This exists so that nobody can guess their way in.

### There is no "Create account" button

Correct. After the first account exists, self sign-up is closed. Accounts are created by the administrator under **Settings → Account → Add someone**. On your own installation, the administrator is you.

---

## Grading

### Grading is stuck on "queued" and never moves

The part of AutoGrade that does the grading is not running.

1. Double-click **Restart AutoGrade**
2. Wait for it to say it is ready, then reload the page

If it happens again, double-click **Show AutoGrade Logs** and look for lines containing `worker`.

### "No AI provider is set up yet"

You have not finished [AI_PROVIDERS.md](AI_PROVIDERS.md). Go to **Settings → AI providers** and set one up. It takes about ten minutes including making the account.

### Every submission fails with "could not reach the server"

| If you use | Check |
|---|---|
| OpenAI or Claude | Your internet connection. Then **Settings → AI providers → Test connection** |
| Ollama | Ollama is running (look for its icon near the clock), and the address is `http://host.docker.internal:11434/v1`, not `localhost` |

### "Incorrect API key" or "authentication failed"

The key is wrong, was revoked, or was copied with a space on the end.

1. **Settings → AI providers**
2. Expand **Replace this key**
3. Make a fresh key at the provider and paste it
4. Click **Test connection**

### "You exceeded your quota" / "insufficient credit"

Your provider account has no money in it. A ChatGPT Plus or Claude Pro subscription does not pay for API use — see [AI_PROVIDERS.md](AI_PROVIDERS.md).

Add credit at <https://platform.openai.com/billing> or <https://console.anthropic.com>.

### Grading is very slow

| If you use | Expect |
|---|---|
| OpenAI / Claude | 15–40 seconds per submission |
| Ollama | 1–3 minutes per submission, longer without a graphics card |

You can close the browser. Grading continues on your computer and you can come back to it.

### Every grade came back as zero, with a warning about the rubric

The AI answered about criteria it invented instead of the ones in your rubric, so none of its scores could be used. **The zeros are not a judgement of your students** - the grade says so itself.

This happens with local Ollama models that are not strong enough. Use a larger model, or switch to OpenAI or Claude under **Settings → AI providers** and grade again. See [AI_PROVIDERS.md](AI_PROVIDERS.md).

### The grades look too generous

If you are using a local model, that is the known weakness — small models mark kindly. Try a larger one (`qwen2.5-coder:14b`) or use OpenAI for real coursework.

If you are using OpenAI or Claude, your rubric is probably too vague. "Implements OLS" is hard to mark; "uses `pinv` rather than `inv`, and handles the singular case" is easy to mark. See [USER_GUIDE.md](USER_GUIDE.md).

### One submission failed while the rest worked

Open **4 · Review results** and look at that student. Usually the file is corrupt, empty, or not one of the supported types. Re-upload a good copy of just that file.

---

## Uploads

### "File too large"

The limit is 50 MB per file. A notebook that large usually has huge embedded images. Ask the student to clear the outputs and re-run, or export it as HTML.

### "Unsupported file type"

AutoGrade reads `.ipynb`, `.html`, `.py`, and `.zip` containing those. A `.pdf` or `.docx` cannot be graded.

### The student names are wrong

AutoGrade guesses names from filenames. Fix them under **3 · Upload & grade** → **Correct a student name or email**.

---

## Canvas

Every Canvas problem and its fix is in [CANVAS.md](CANVAS.md#common-problems).

---

## Data and backups

### I deleted a course by mistake

Restore last night's backup — see [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md). Note that this also rolls back anything graded since.

### I need to move AutoGrade to a new computer

1. On the old computer: double-click **Backup AutoGrade**
2. Copy both files from the `backups` folder onto a USB stick
3. On the new computer: install AutoGrade ([INSTALL.md](INSTALL.md)) and start it once
4. Copy the two files into the new `backups` folder
5. Double-click **Restore AutoGrade**
6. Add your AI key and Canvas token again under **Settings**

### Is my student data safe if my laptop is stolen?

The data is on the disk. If your Windows account has a password and the disk is encrypted with BitLocker, a thief cannot read it. If not, they can. Ask your IT department to turn BitLocker on — it takes them a minute and it protects everything on the machine, not just AutoGrade.

---

## Starting completely over

**This deletes every course, grade and file in AutoGrade.** Back up first if there is anything you want.

1. Double-click **Stop AutoGrade**
2. Open PowerShell in the AutoGrade folder and run:

```bash
docker compose -f docker-compose.local.yml down -v
```

3. Delete the `.env` file in the AutoGrade folder
4. Double-click **Start AutoGrade**

You get a fresh, empty AutoGrade and create your account again.

---

## Getting help

Send whoever supports you these three things. None of them contains your password, your API key, or any student's work.

1. **What you did, and what you saw instead of what you expected.** One or two sentences is enough.
2. **A screenshot** of the error.
3. **The logs:** double-click **`Show AutoGrade Logs`**, right-click in the black window, choose **Select All**, press **Enter** to copy, and paste it into your message.
