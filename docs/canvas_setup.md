# Connecting Canvas

Each instructor connects their own Canvas account. The token is encrypted
before it is stored and is used only for that person's own requests, so on
a shared instance every professor pushes into their own courses.

## Get a token from Canvas

1. Sign in to Canvas.
2. **Account** (your picture, top-left) → **Settings**.
3. Scroll to **Approved Integrations** → **+ New Access Token**.
4. Purpose: `AutoGrade`. Leave the expiry blank, or set a date and
   remember to make a new one when it lapses.
5. **Generate Token**, then copy it immediately — Canvas shows it once.

The token acts as you, across every course you teach, with read and write
access. Treat it like a password. Revoking it on that same Canvas page
stops AutoGrade using it at once.

## Give it to AutoGrade

**Settings → Canvas** → paste the Canvas URL and the token → **Save**, then
**Test connection**. A successful test names the Canvas account the token
belongs to, which is the quickest way to catch a token pasted from the
wrong browser profile.

## Then

Set the **Canvas course ID** on the course and the **Canvas assignment ID**
on the assignment, and **5 · Export → Canvas** can sync the roster and push
approved grades.

## Server-wide configuration

A single-instructor install can skip all of the above and set
`CANVAS_BASE_URL` and `CANVAS_API_TOKEN` in `.env` instead. Anyone who has
connected their own account under Settings uses theirs; everyone else falls
back to the server's. On an instance with more than one instructor, connect
per-instructor accounts — one shared token cannot write grades into another
professor's course.
