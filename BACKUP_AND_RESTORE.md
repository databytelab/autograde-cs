# Backups

Your courses, rubrics, grades and uploaded files live on this computer and nowhere else. If the computer dies, they die with it — unless you have a copy somewhere else.

Reading this takes five minutes. Doing it takes two.

---

## What is already happening

While AutoGrade is running, it saves a copy of the gradebook **every 24 hours** into the `backups` folder inside your AutoGrade folder, and keeps the last 30 days.

That protects you from a mistake — deleting a course, a bad grade import. **It does not protect you from losing the computer**, because the copy is on the same disk.

---

## Make a backup right now

1. Open your AutoGrade folder
2. Double-click **`Backup AutoGrade`**

**Expected result:**

```
  OK   Saved to the backups folder:
     autograde-2026-03-14-1130.dump          the gradebook
     autograde-2026-03-14-1130-files.tgz     the submitted files
```

Two files, because grades and student files are stored separately. **You need both** — restoring one without the other gives you grades with nothing attached, or files with no grades.

Do this before:

- Updating AutoGrade
- Anything you are nervous about
- The end of term

---

## Copy it somewhere else

This is the step that actually protects you.

1. Open your AutoGrade folder
2. Open the **`backups`** folder
3. Select the newest `.dump` file **and** its matching `-files.tgz`
4. Copy them (**Ctrl+C**)
5. Paste them (**Ctrl+V**) onto:
   - a USB stick, **or**
   - your university OneDrive / Google Drive folder, **or**
   - any other computer

Do this at least once a month, and always at the end of term.

> If your university gives you a synced Drive folder, drop a copy there and it happens by itself from then on.

---

## Restore from a backup

This replaces **everything** currently in AutoGrade with the contents of the backup. Anything graded since that backup was taken is lost.

1. Make sure AutoGrade is running — double-click **`Start AutoGrade`** if not
2. Double-click **`Restore AutoGrade`**
3. It lists your backups, newest first:

   ```
     Which backup?

       1) autograde-2026-03-14-1130.dump   (14 Mar 2026, 11:30)
       2) autograde-2026-03-13-1130.dump   (13 Mar 2026, 11:30)
   ```

4. Type the number and press **Enter**
5. It asks you to confirm. Type `RESTORE` in capitals and press **Enter**
6. Wait. It stops AutoGrade, puts the data back, and starts it again

**Expected result:**

```
  OK   Submitted files restored
  OK   Restored. Open AutoGrade and check a course you recognise.
```

7. Open AutoGrade and check that a course you remember is there, with its grades

### Restoring from a copy you took away

If you are restoring from a USB stick or a new computer:

1. Install AutoGrade on the new computer (see [INSTALL.md](INSTALL.md)) and start it once
2. Copy both backup files into the `backups` folder inside the new AutoGrade folder
3. Double-click **`Restore AutoGrade`** and pick your backup

Your account, courses and grades all come back. **Your AI key and Canvas token do not** — those are encrypted with a secret unique to each installation. Add them again under **Settings**; it takes two minutes.

---

## Practise it once

An untested backup is a guess.

Before you rely on AutoGrade for real grading, do this once:

1. Create a course called `Practice` with one assignment
2. Double-click **Backup AutoGrade**
3. Delete the `Practice` course in AutoGrade
4. Double-click **Restore AutoGrade** and pick that backup
5. Check that `Practice` is back

Ten minutes now, and you will know it works.

---

## Common problems

| What you see | What to do |
|---|---|
| *Could not back up the gradebook* | AutoGrade is not running. Double-click **Start AutoGrade** first |
| *There are no backups in the backups folder* | Double-click **Backup AutoGrade** to make one |
| *No matching files archive* | The `-files.tgz` beside the `.dump` is missing. Grades come back; the original submissions do not |
| The restore finished but a course is missing | That course was created after the backup was taken. Backups only contain what existed at the time |
| AutoGrade will not start after a restore | Double-click **Restart AutoGrade**. If it still fails, restore a different backup |

---

## What is in a backup, and what is not

**In it:**

- Your account and any colleagues' accounts
- Courses, assignments and rubrics
- Submissions, grades, your overrides and approvals
- Similarity flags
- The uploaded student files (in the `-files.tgz`)

**Not usable from it:**

- Your AI provider key and your Canvas token. They are in the backup, but encrypted with a secret that belongs to *this* installation — so restoring onto a different computer brings back the rows and not the keys, and a stolen backup does not hand anyone your accounts. Restoring onto the same installation keeps them working.

**Not in it at all:**

- AutoGrade itself. Keep the ZIP you were given, or ask for it again
