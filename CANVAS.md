# Connecting Canvas

**Optional.** Without Canvas, AutoGrade still exports CSV, Excel and PDF, and you upload those to Canvas by hand. With Canvas connected, approved grades go straight into your gradebook.

**Time needed:** about 10 minutes.

---

## Step 1 — Get an access token from Canvas

A token is a long password that lets AutoGrade act as you in Canvas.

1. Open Canvas in your browser and sign in
2. Click **Account** — your photo, at the top-left
3. Click **Settings**
4. Scroll down to **Approved Integrations**
5. Click **+ New Access Token**
6. **Purpose:** type `AutoGrade`
7. **Expires:** leave it blank. (If you set a date, you will have to repeat all of this when it passes)
8. Click **Generate Token**
9. **Copy the token now.** Canvas shows it once and never again

**Expected result:** a long string of letters and numbers on your clipboard.

> The token acts as you, in every course you teach, and can change grades. Treat it like your password. Do not email it to anyone.

---

## Step 2 — Give it to AutoGrade

1. In AutoGrade, click **Canvas** under **Settings** in the sidebar
2. **Canvas web address** — type the address you use to open Canvas, for example:

   ```
   https://canvas.your-university.edu
   ```

   Just the site address. Nothing after it — no `/courses/1234`.

3. **Access token** — paste what you copied
4. Click **Connect**
5. Click **Test connection**

**Expected result:** a green message naming your Canvas account, for example *Connected as Dr Ada Lovelace*.

If it names somebody else, you copied a token from a different Canvas login. Use **Replace the token**.

---

## Step 3 — Link your course and assignment

AutoGrade needs to know which Canvas course and which Canvas assignment to write into. Both are numbers you can read off the Canvas web address.

### Find the course ID

1. Open your course in Canvas
2. Look at the address bar:

   ```
   https://canvas.your-university.edu/courses/12345
                                              ^^^^^
   ```

3. `12345` is your **Canvas course ID**

### Find the assignment ID

1. Open the assignment in Canvas
2. Look at the address bar:

   ```
   https://canvas.your-university.edu/courses/12345/assignments/67890
                                                                ^^^^^
   ```

3. `67890` is your **Canvas assignment ID**

### Put them into AutoGrade

1. Click **2 · New assignment** in the sidebar
2. Expand **Courses**, select your course, and put the number into **Canvas course ID**
3. Save
4. Select your assignment and put the number into **Canvas assignment ID**
5. Save

---

## Step 4 — Match your students to Canvas

AutoGrade guesses student names from filenames. Before pushing grades, it checks those guesses against your real Canvas roster.

1. Click **5 · Export** in the sidebar
2. Choose the course and assignment
3. Scroll to **Canvas**
4. Click **1 · Sync roster**

**Expected result:** a count of how many submissions were matched, and a list of any that were not.

Anything that cannot be matched confidently is listed rather than guessed. Fix those under **3 · Upload & grade → Correct a student name or email**, then sync again.

---

## Step 5 — Push the grades

1. Still on **5 · Export**, under **Canvas**
2. Leave **Approved grades only** ticked
3. Click **Push to Canvas**

**Expected result:** a count of grades pushed, and any that were skipped with the reason.

Open Canvas and check the gradebook. Scores are sent as percentages, so a rubric out of 100 lands correctly on a Canvas assignment worth 6 points, or any other value.

> Only grades you have **approved** are pushed. Unticking that box pushes unreviewed AI proposals into a real gradebook — do not.

---

## Changing or removing the connection

All of these are on **Settings → Canvas**.

| To | Do this |
|---|---|
| Fix a typo in the address | Expand **Change the Canvas web address**. Your token is kept |
| Use a new token | Expand **Replace the token**, paste the new one |
| Stop AutoGrade using Canvas | Expand **Remove this connection**, click **Remove connection** |

### Revoking a token in Canvas

Removing the connection makes AutoGrade forget the token. To make the token itself stop working everywhere:

1. In Canvas: **Account** → **Settings**
2. Scroll to **Approved Integrations**
3. Find the row named `AutoGrade`
4. Click the **bin** icon, and confirm

Do this if you ever think the token has been seen by someone else.

---

## Common problems

| What you see | What it means | What to do |
|---|---|---|
| *Canvas rejected the token* | Wrong, expired, or revoked | Make a new token (step 1) and use **Replace the token** |
| *Could not reach Canvas* | The address is wrong, or you are off the university network | Check the address has no `/courses/...` on the end. Try opening it in a browser |
| *Connected as* somebody else | Token copied from another Canvas account | Make a token while signed in as yourself |
| The course list is empty | The token has no teacher role in any course | Check you are a teacher, not an observer, in Canvas |
| *This course has no Canvas course ID* | Step 3 not done | Add the number from the Canvas address bar |
| Push says *skipped: not finalized* | Those grades are not approved yet | Approve them under **4 · Review results** |
| Push says *skipped: no Canvas student* | The roster sync could not match that student | Correct the student's name or email, sync the roster again |

---

## What AutoGrade does and does not do in Canvas

**It does:**

- Read your course list and your roster
- Write the score for the assignment you linked
- Attach your summary feedback as a submission comment

**It does not:**

- Change anything in any course you did not link
- Publish, unpublish, or alter assignments
- Touch grades you have not approved
- Message students
