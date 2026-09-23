# Development

Running AutoGrade from source, the test suite, and building the release a professor receives.

For installing AutoGrade to actually use it, see [INSTALL.md](../../INSTALL.md) — that path is one double-click and does not involve any of this.

---

## Run from source

```bash
python -m venv venv
```

```bash
venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Set these three in `.env`:

```ini
ENVIRONMENT=development
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

```bash
alembic upgrade head
```

Then three terminals:

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

```bash
python -m backend.worker
```

```bash
python -m streamlit run frontend_streamlit/app.py
```

- App: <http://localhost:8501>
- API docs: <http://localhost:8000/docs>

Terminal 2 is the grading worker. Grading is a durable background job, so without it a job is accepted and stays `queued` forever.

Development mode uses SQLite, leaves self sign-up open, and skips the production safety checks.

### Demo data

```bash
python scripts/seed_demo_data.py --reset --fake-grades
```

Seeds a course, an assignment, and nine varied submissions — a plagiarised pair, an unrun notebook, a corrupt file — and signs you in as `demo@university.edu` / `demo-password-123`. Use `--grade` for real grading instead of placeholders.

### Grade one real submission end to end

```bash
python scripts/smoke_test.py --student Lab2_Tasks_student_submission.html --solution Lab2_DT_Solution.html
```

Prints the provider, the model, a full scorecard and token usage.

---

## The three ways it runs

| File | For | Started by |
|---|---|---|
| none | Working on the code | the three commands above |
| `docker-compose.local.yml` | **What a professor installs.** One computer, loopback only, no HTTPS | `Start AutoGrade` / `./autograde.sh` |
| `docker-compose.prod.yml` | A department server for many people, behind Caddy with real HTTPS | `setup.sh` / `setup.ps1` |

`docker-compose.yml` is the older development compose stack; the three-terminal flow above is usually more convenient.

The professor-facing path is `docker-compose.local.yml`. It is the one that must stay simple — anything that adds a question to first-run belongs in the server stack instead.

---

## Tests

```bash
pytest
```

No network access, no API key required — the LLM client is replaced with a scripted fake for every provider.

| File | Covers |
|---|---|
| `test_parsers.py` | the shared parse contract across all three formats, plus corrupt/empty/unrun inputs |
| `test_rubric_engine.py` | validation, normalisation, letter-grade boundaries |
| `test_grader.py` | the trust boundary — clamping, missing criteria, bad JSON, every API failure path |
| `test_providers.py` | the provider switch — factory selection, request shape, parsing, usage, error translation |
| `test_similarity.py` | rename-invariance, false-positive resistance, winnowing properties |
| `test_jobs.py` | the durable queue — claiming, heartbeats, crash recovery, cancellation |
| `test_api.py` | every endpoint: status codes, auth, ownership isolation, validation |
| `test_provider_credentials.py` | per-professor keys: encryption, masking, isolation, never logged |
| `test_accounts_and_canvas.py` | first-account bootstrap, closed sign-up, admin actions, per-instructor Canvas |
| `test_audit_regressions.py` | every issue found in the security and performance audit, reproduced first |
| `test_full_pipeline.py` | the whole workflow end to end, plus cascade deletes and mid-batch failures |
| `test_frontend.py` | every Streamlit page renders, via Streamlit's `AppTest` |

Streamlit is pinned at 1.35.0. `st.experimental_dialog`, not `st.dialog`; there is no `st.segmented_control`.

---

## Project layout

```
backend/
  ai/            grader.py, prompts.py, image_evaluator.py
    providers/   the LLM switch: openai / anthropic / local, one interface
  parsers/       notebook / html / python, behind parser_router.py
  services/      rubric, grading orchestration, jobs, credentials, export, Canvas
  routers/       FastAPI endpoints
  models/        SQLAlchemy models
  schemas/       Pydantic request/response models
  utils/         auth, file storage, similarity detection
  worker.py      the background grading worker
frontend_streamlit/
  app.py         sign-in and workflow hub
  pages/         dashboard, new assignment, upload & grade, review, export, settings
alembic/         database migrations
docker/          Dockerfiles, Caddyfile, entrypoint, backup
scripts/         autograde.ps1 (the Windows launcher), demo data, smoke test, packaging
tests/           the suite above, plus sample_submissions/
docs/developer/  this folder
```

---

## Configuration

A professor never edits `.env` — their AI provider and Canvas connection are set in the interface, and the launcher writes every other value. These matter when running from source or on a server.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enforces the checks below |
| `LLM_PROVIDER` | `openai` | Server-wide default. Users may override it per account |
| `OPENAI_API_KEY` | — | Optional. Grading also works from per-user keys |
| `ANTHROPIC_API_KEY` | — | Same |
| `LOCAL_BASE_URL` | `http://localhost:11434/v1` | `host.docker.internal` from inside a container |
| `SECRET_KEY` | — | Signs JWTs. Production refuses to start on a default or short value |
| `CREDENTIAL_ENCRYPTION_KEY` | — | Encrypts saved API and Canvas tokens. Set it and never change it |
| `DATABASE_URL` | `sqlite:///./autograde.db` | Production refuses SQLite |
| `ALLOW_OPEN_REGISTRATION` | `false` | The first account is always allowed regardless |
| `AUTOGRADE_PORT` | `8501` | Local install only; the launcher picks a free one |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 8 hours |
| `UPLOAD_DIR` | `./uploads` | Student files. Back this up |
| `MAX_FILE_SIZE_MB` | `50` | Enforced while streaming, before the file lands |
| `CANVAS_BASE_URL` / `CANVAS_API_TOKEN` | empty | Optional server-wide fallback |

### What production refuses to start on

A default, short, or placeholder `SECRET_KEY`; a SQLite or default `DATABASE_URL`.

**Not** an unconfigured AI provider — that is a warning. A professor sets their provider in the interface after the application is running, and refusing to boot without a key in `.env` would send them into the one file the design promises they never have to open.

---

## Building the release

```bash
git tag -a v1.0.0 -m "..."
```

```bash
python scripts/package_release.py
```

Writes `dist/autograde-<tag>.zip` from committed files only, then reopens the archive and refuses to ship if anything inside matches the shape of a live API key or Canvas token. It also checks that the files a professor needs on first run are present.

What the recipient does with it is [INSTALL.md](../../INSTALL.md).

---

## Things that have bitten us

- **The worker needs egress.** Marking its Docker network `internal: true` severed it and every submission failed with "could not reach the openai server".
- **A blank `OPENAI_BASE_URL` exported by `env_file`** made the SDK build a scheme-less URL. The provider now falls back to an explicit default.
- **Caddy's `{$VAR:default}` only substitutes when the variable is unset**, not when it is empty. Defaults belong in compose's `:-` instead.
- **The worker inherits the API image's healthcheck**, which curls a port it does not listen on. It is disabled explicitly.
- **Windows line endings.** `.gitattributes` pins `*.sh` to LF and `*.bat` to CRLF; without it a Windows clone produces a container entrypoint that cannot exec.
- **`docker compose` is not always discoverable** from Git Bash. The launchers fall back to `docker-compose` and then to the Docker Desktop plugin binary.
