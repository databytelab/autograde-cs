# AutoGrade CS

AI-assisted grading for CS assignments. Upload a class's `.ipynb`, `.html`, `.py` or `.zip` submissions, grade them against your rubric with **OpenAI, Anthropic Claude, or a local model (e.g. Qwen)**, review and adjust every result, then export to CSV, Excel, PDF, or Canvas.

**You approve every grade.** Nothing reaches a student or a gradebook until a professor finalizes it.

---

## Start here

| I want to | Read |
|---|---|
| Install it | **[INSTALL.md](INSTALL.md)** |
| Use it to grade | **[USER_GUIDE.md](USER_GUIDE.md)** |
| Run the server day to day | **[RUN_AND_SHARE.md](RUN_AND_SHARE.md)** |
| Decide where to host it | **[CHOOSING_YOUR_SETUP.md](CHOOSING_YOUR_SETUP.md)** |
| Understand the architecture | **[DEPLOYMENT.md](DEPLOYMENT.md)** |

Fastest install — Docker Desktop and nothing else:

```bash
./setup.sh
```

```powershell
.\setup.ps1
```

The first account created becomes the administrator. Full steps in [INSTALL.md](INSTALL.md).

---

## What it does

- **Parses** notebooks, nbconvert HTML exports, and plain Python — cells, code, prose, outputs, figures, and tracebacks.
- **Grades** each submission against your rubric in one model call, with per-criterion scores, student-facing feedback, and the grader's reasoning kept as an audit trail.
- **Verifies** the model's work: totals are recomputed in Python, scores are clamped to each criterion's maximum, and any criterion the model skipped is filled in and flagged. *The model never does arithmetic that counts.*
- **Flags** unrun notebooks, recorded runtime errors, possible AI-generated work, and submissions that try to instruct the grader.
- **Detects similarity** between submissions using normalised tokens plus AST structure, so renaming variables does not hide a copy.
- **Exports** to CSV, Excel (with a per-criterion sheet), per-student PDF feedback sheets, or straight into the Canvas gradebook.

## How grading works

1. **Parse** — every submission becomes one common structure, so the grader never has to care what format it started as.
2. **Queue** — grading is a durable background job. Close the browser; it keeps running. A crashed worker resumes without re-grading what was already done.
3. **Grade** — the rubric goes to the model verbatim, followed by the submission cell by cell with its recorded outputs and up to four figures.
4. **Verify** — `normalize_grade` recomputes the total, clamps every score to its criterion maximum, inserts any criterion the model omitted with a `grader_error` flag, and adds deterministic flags that do not depend on the model noticing them.
5. **Review** — you adjust what you disagree with and approve. Overrides are stored beside the AI scores, so the record shows both.

---

## Development setup

For working on the code. To run it for real, use [INSTALL.md](INSTALL.md).

```bash
git clone https://github.com/databytelab/autograde-cs.git
```

```bash
cd autograde-cs
```

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

Then **three** terminals:

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

Terminal 2 is the grading worker. Without it, jobs stay queued forever.

### Demo data

```bash
python scripts/seed_demo_data.py --reset --fake-grades
```

Seeds a course, an assignment, and nine varied submissions — including a plagiarised pair, an unrun notebook, and a corrupt file — then signs you in with `demo@university.edu` / `demo-password-123`. Use `--grade` for real grading instead of placeholders.

### Grade one real submission end to end

```bash
python scripts/smoke_test.py --student Lab2_Tasks_student_submission.html --solution Lab2_DT_Solution.html
```

Prints the provider, the model, a full scorecard, and token usage.

---

## Switching the AI provider

Set `LLM_PROVIDER` in `.env` and restart. Nothing else changes. Individual professors can override the server default under **Settings → AI providers**.

**OpenAI (default)**

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_GRADING_MODEL=gpt-4o
```

**Anthropic Claude**

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_GRADING_MODEL=claude-opus-5
```

**Local model (Ollama / vLLM / LM Studio)**

```ini
LLM_PROVIDER=local
LOCAL_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL=qwen2.5-coder:7b
```

Use `http://host.docker.internal:11434/v1` when AutoGrade runs in Docker. A text-only local model still grades code; use a vision model to grade plots.

## Rubrics

Four ways to define one: upload a solved reference file, paste the assignment brief, write the JSON yourself, or start from the default CS rubric. Field reference in [`docs/rubric_format.md`](docs/rubric_format.md).

## Canvas

Each instructor connects their own Canvas account under **Settings → Canvas**; a single-instructor install can instead set `CANVAS_BASE_URL` and `CANVAS_API_TOKEN` in `.env`. See [`docs/canvas_setup.md`](docs/canvas_setup.md). Without Canvas, the Canvas CSV export still works.

---

## Testing

```bash
pytest
```

363 tests, no network access, no API key required — the LLM client is replaced with a scripted fake for every provider.

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
scripts/         demo data, smoke test, benchmark, release packaging
tests/           the suite above, plus sample_submissions/
docs/            rubric format, API reference, Canvas setup
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enforces the safety checks below |
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, or `local` |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `OPENAI_GRADING_MODEL` | `gpt-4o` | Needs vision + strict JSON |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic` |
| `LOCAL_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible URL when provider is `local` |
| `LOCAL_MODEL` | `qwen2.5-coder:7b` | The local model to grade with |
| `SECRET_KEY` | — | Signs JWTs. Production refuses to start on a default or short value |
| `CREDENTIAL_ENCRYPTION_KEY` | — | Encrypts saved API and Canvas tokens. Set it and never change it |
| `DATABASE_URL` | `sqlite:///./autograde.db` | Production refuses SQLite |
| `ALLOW_OPEN_REGISTRATION` | `false` | Production closes self sign-up. The first account is always allowed |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 8 hours |
| `UPLOAD_DIR` | `./uploads` | Student files. Back this up |
| `MAX_FILE_SIZE_MB` | `50` | Enforced while streaming, before the file lands |
| `CANVAS_BASE_URL` / `CANVAS_API_TOKEN` | empty | Optional server-wide fallback |

## Limitations

- **No student-facing interface.** This is an instructor tool.
- **No reset-by-email.** A forgotten password needs the administrator.
- **Similarity flags are prompts to look, not verdicts.** Two students who worked from the same lecture example will legitimately look alike.
- **Small local models are lenient.** Spot-check before trusting one.
- **Single host.** Backups protect the data, not the uptime.
- **The model can be wrong.** That is why nothing is final until you say so, and why the raw model output is kept for every grade.

## Licence

MIT — see [LICENSE](LICENSE).
