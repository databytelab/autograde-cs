# Running AutoGrade day to day

Everything here is a button in your AutoGrade folder. There are no commands to learn.

To install it in the first place, see **[INSTALL.md](INSTALL.md)**.

---

## The buttons

| Double-click | What it does |
|---|---|
| **Start AutoGrade** | Starts everything and opens it in your browser |
| **Stop AutoGrade** | Shuts it down. Nothing is lost |
| **Restart AutoGrade** | Stop, then start. The first thing to try if anything looks odd |
| **Update AutoGrade** | Installs a newer version you have unpacked over this folder |
| **Backup AutoGrade** | Saves a copy of everything into the `backups` folder |
| **Restore AutoGrade** | Puts a saved copy back |
| **Show AutoGrade Logs** | Prints what AutoGrade has been doing. For when you ask for help |

---

## Starting and stopping

### Open AutoGrade

Double-click **`Start AutoGrade`**.

It takes about twenty seconds, then your browser opens at `http://localhost:8501`.

**Expected result:**

```
  OK   Docker is running
  OK   Database, grading worker and interface are all running

AutoGrade is ready
  Opening http://localhost:8501 in your browser.
```

### Close AutoGrade

Double-click **`Stop AutoGrade`**.

Your courses, grades and files stay exactly where they are. Start it again whenever you like.

### Do I have to stop it?

No. Leaving it running costs almost nothing, and it starts again by itself when you turn your computer on. Stop it if you want the memory back, or before travelling.

### Closing the black window

Closing the window does not stop AutoGrade. Only **Stop AutoGrade** does.

### Is it running?

Open <http://localhost:8501>. If the sign-in page appears, it is running.

---

## Bookmark it

1. Open <http://localhost:8501> in your browser
2. Press **Ctrl+D**
3. Name it `AutoGrade`

You can also pin **Start AutoGrade** to your taskbar: right-click it → **Pin to taskbar**.

---

## Updating to a new version

You will be sent a new ZIP file.

1. Double-click **`Backup AutoGrade`** and wait for it to finish
2. Extract the new ZIP somewhere temporary
3. Copy everything from inside it **into your existing AutoGrade folder**, replacing files when Windows asks
   - Do **not** delete your existing folder. Your `.env` and `backups` must stay
4. Double-click **`Update AutoGrade`**

**Expected result:**

```
  OK   Updated and running
```

Your courses, grades, files, AI key and Canvas connection all survive. Update takes its own backup first, so if anything goes wrong you can use **Restore AutoGrade** to go back.

---

## Backups

Covered properly in **[BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md)**. The short version:

- A copy is saved automatically every 24 hours while AutoGrade runs
- Double-click **Backup AutoGrade** before anything risky
- **Copy the `backups` folder to a USB stick or your university Drive once a month.** A backup on the same computer does not survive losing the computer

---

## Adding a colleague on this computer

Only useful if you share a computer, for example a lab machine or a shared office PC. For a colleague with their own laptop, give them the AutoGrade ZIP and [INSTALL.md](INSTALL.md) instead — their data then stays on their own machine.

1. Click **Account** under **Settings** in the sidebar
2. Scroll to **Add someone**
3. **Full name** and **Email**
4. Copy the **Initial password** it fills in for you
5. **Role** — `professor` can approve grades; `ta` can grade and comment but not approve
6. Click **Create account**
7. Send them the address `http://localhost:8501`, their email, and that password

They sign in and change it under **Settings → Account → Change your password**.

Each person sees only their own courses. Nobody can see anyone else's, and each sets up their own AI key.

### Reset someone's password

**Settings → Account → People**, expand their name, type a new password, click **Reset password**.

### Someone has left

**Settings → Account → People**, expand their name, click **Deactivate**. They can no longer sign in. Their courses stay.

---

## Letting people reach it from another computer

By default AutoGrade answers only on the computer it is installed on. This is deliberate — it means nothing on your network can reach your students' work.

If you need several people on different machines to share one AutoGrade, that is a departmental server rather than a laptop installation. Ask whoever supplies AutoGrade; it is a different setup and it needs somebody who looks after servers.

---

## What is actually running

Five small programs, started and stopped together by the buttons above:

| | |
|---|---|
| **frontend** | The pages you click on |
| **api** | Answers the pages, stores your data |
| **worker** | Does the grading, one submission at a time |
| **db** | The gradebook |
| **backup** | Saves a copy every 24 hours |

You never have to interact with any of them. If one stops, the others keep going and it restarts by itself.

---

## Common questions

**Does AutoGrade slow my computer down?**
Idle, barely. While grading, one processor core is busy for a few minutes. With a local Ollama model, it uses a lot more memory — that is the model, not AutoGrade.

**Can I use my computer while it grades?**
Yes. You can also close the browser and come back later.

**Does it need the internet?**
Only for grading with OpenAI or Claude. With Ollama, it works with the internet unplugged.

**What happens if my computer sleeps mid-grading?**
Grading pauses and picks up where it left off when the computer wakes. Nothing is lost or paid for twice.

**Where are my files kept?**
In Docker's storage on this computer, and copies of everything in the `backups` folder inside your AutoGrade folder.

**Can I move the AutoGrade folder?**
Stop AutoGrade first, move the whole folder, then start it again. Do not move it while it is running.

**How do I remove AutoGrade completely?**
See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#starting-completely-over), then delete the folder and uninstall Docker Desktop.
