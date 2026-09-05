# AutoGrade CS

AI-assisted grading for CS assignments. Upload a class's `.ipynb`,
`.html`, or `.py` submissions, grade them against your rubric with the AI
of your choice — **OpenAI by default, or Anthropic Claude, or a local model
(e.g. Qwen)** — review and adjust every result, then export to CSV, Excel,
PDF, or Canvas.

**You approve every grade.** Nothing reaches a student or a gradebook
until a professor finalizes it.

---

## Documentation

| Read this | If you are |
|---|---|
| **[USER_GUIDE.md](USER_GUIDE.md)** | An instructor using AutoGrade. Click-by-click, no technical knowledge needed. |
| **[CHOOSING_YOUR_SETUP.md](CHOOSING_YOUR_SETUP.md)** | Deciding *where* to run it. Explains where student data goes and who can read it. **Read this before sharing with colleagues.** |
| **[RUN_AND_SHARE.md](RUN_AND_SHARE.md)** | Running the server: install, start/stop, logs, backups, upgrades, AI providers, inviting people. |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | The architecture reference: services, volumes, ports, risks. |

## What it does

- **Parses** notebooks, nbconvert HTML exports, and plain Python — cells,
  code, prose, outputs, figures, and tracebacks.
- **Grades** each submission against your rubric in one Claude call, with
  per-criterion scores, student-facing feedback, and the grader's
  reasoning kept as an audit trail.
- **Verifies** the model's work: totals are recomputed in Python, scores
  are clamped to each criterion's maximum, and any criterion the model
  skipped is filled in and flagged. *The model never does arithmetic that
  counts.*
- **Flags** unrun notebooks, recorded runtime errors, and possible
  AI-generated work.
- **Detects similarity** between submissions using normalised tokens plus
  AST structure, so renaming variables does not hide a copy.
- **Exports** to CSV, Excel (with a per-criterion sheet), per-student PDF
  feedback sheets, or straight into the Canvas gradebook.

## Stack

- **Backend** — FastAPI, SQLAlchemy, Alembic (Python 3.11)
- **Frontend** — Streamlit
- **AI** — pluggable: OpenAI (default), Anthropic Claude, or any local
  OpenAI-compatible server (vLLM, Ollama, LM Studio). Set `LLM_PROVIDER`.
- **Database** — SQLite for development, PostgreSQL for production

---

## Quick start

```bash
git clone https://github.com/databytelab/autograde-cs.git
cd autograde-cs

python -m venv venv
venv\Scripts\activate          # Windows;  source venv/bin/activate elsewhere
pip install -r requirements.txt

cp .env.example .env           # then edit it — see below
alembic upgrade head
```

Two things must go in `.env` before grading works. By default the grader
uses OpenAI:

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
```

To use Claude or a local model instead, see
[Switching the AI provider](#switching-the-ai-provider) below.

Run the backend and the frontend in separate terminals:

```bash
uvicorn backend.main:app --reload
```

```bash
streamlit run frontend_streamlit/app.py
```

- App: <http://localhost:8501>
- API docs: <http://localhost:8000/docs>

### Try it with demo data

```bash
python scripts/seed_demo_data.py --reset --fake-grades
```

Seeds a course, an assignment, and nine varied submissions — including a
plagiarised pair, an unrun notebook, and a corrupt file — then signs you
in with `demo@university.edu` / `demo-password-123`. `--fake-grades`
writes obvious placeholders so the review and export screens have
something to show without spending API credits; use `--grade` for real
grading.

### Docker

```bash
docker compose up --build
```

See [`docker/README.md`](docker/README.md) for the PostgreSQL profile and
volume details.

---

## How grading works

1. **Parse** — every submission becomes one common structure regardless of
   format, so the grader never has to care whether it started as a
   notebook or a `.py` file.
2. **Grade** — the rubric goes to the model verbatim, followed by the
   submission rendered cell by cell with its recorded outputs, plus up to
   four figures. Structured outputs guarantee a parseable response. The
   model is whichever `LLM_PROVIDER` selects; the rest of the pipeline
   does not change.
3. **Verify** — this is the part that matters. `normalize_grade` recomputes
   the total, clamps every score to its criterion maximum, inserts any
   criterion the model omitted with a `grader_error` flag, and adds
   deterministic flags (`no_outputs`, `runtime_error`) that do not depend
   on the model noticing them.
4. **Review** — you read the feedback, adjust what you disagree with, and
   approve. Overrides are stored *beside* the AI scores, so the record
   always shows both what the model said and what you decided.

## Rubrics

Three ways to define one — paste prose and let Claude extract the
criteria, write the JSON yourself, or upload a solved reference notebook.
Full field reference and guidance in
[`docs/rubric_format.md`](docs/rubric_format.md).

## Canvas

Optional. Set `CANVAS_BASE_URL` and `CANVAS_API_TOKEN` to sync the roster
and push grades back. Without them the Canvas CSV export still works.
See [`docs/canvas_setup.md`](docs/canvas_setup.md).

---

## Switching the AI provider

Grading works with three interchangeable backends. Set `LLM_PROVIDER` in
`.env` and restart the server — nothing else changes.

**OpenAI (default)**

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_GRADING_MODEL=gpt-4o        # needs vision + strict JSON
```

**Anthropic Claude**

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_GRADING_MODEL=claude-opus-5
```

**Local model (Qwen via Ollama / vLLM / LM Studio)**

No API key, no data leaving your machine. Start a local server that speaks
the OpenAI API, then:

```ini
LLM_PROVIDER=local
LOCAL_BASE_URL=http://localhost:11434/v1   # Ollama shown; vLLM :8000, LM Studio :1234
LOCAL_MODEL=qwen2.5-coder:7b               # use a vision model (e.g. qwen2.5-vl) to grade figures
```

With Ollama that is just `ollama serve` and `ollama pull qwen2.5-coder`.
A text-only local model still grades code; to grade plots, use a
vision-capable model or pass `--no-images` to the smoke test.

### Verify it works (smoke test)

Grade one real submission end to end with whatever provider is active:

```bash
python scripts/smoke_test.py \
  --student Lab2_Tasks_student_submission.html \
  --solution Lab2_DT_Solution.html
```

It prints the provider, the model, a full scorecard, and the token usage —
the quickest way to confirm a new provider or key is wired up correctly.

## Testing

```bash
pytest
```

249 tests, no network access, no API key required — the LLM client is
replaced with a scripted fake for every provider.

| File | Covers |
|------|--------|
| `test_parsers.py` | the shared parse contract across all three formats, plus corrupt/empty/unrun inputs |
| `test_rubric_engine.py` | validation, normalisation, letter-grade boundaries |
| `test_grader.py` | the trust boundary — clamping, missing criteria, bad JSON, every API failure path (Anthropic) |
| `test_providers.py` | the provider switch — factory selection, the OpenAI/local request shape, parsing, usage, and error translation |
| `test_similarity.py` | rename-invariance, false-positive resistance, winnowing properties |
| `test_api.py` | every endpoint: status codes, auth, ownership isolation, validation |
| `test_full_pipeline.py` | the whole workflow end to end, plus cascade deletes and mid-batch failures |
| `test_frontend.py` | every Streamlit page renders, via Streamlit's `AppTest` |

## Project layout

```
backend/
  ai/            grader.py, prompts.py, image_evaluator.py
    providers/   the LLM switch: openai / anthropic / local, one interface
  parsers/       notebook / html / python, behind parser_router.py
  services/      rubric, grading orchestration, export, Canvas
  routers/       FastAPI endpoints
  models/        SQLAlchemy models
  schemas/       Pydantic request/response models
  utils/         auth, file storage, similarity detection
frontend_streamlit/
  app.py         sign-in and workflow hub
  pages/         dashboard, new assignment, upload & grade, review, export
tests/           the suite above, plus sample_submissions/
docs/            rubric format, API reference, Canvas setup
```

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | `openai` | Which AI grades: `openai`, `anthropic`, or `local`. |
| `OPENAI_API_KEY` | — | Required when provider is `openai`. |
| `OPENAI_GRADING_MODEL` | `gpt-4o` | Any model your account can call (needs vision + JSON). |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic`. |
| `LOCAL_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible URL when provider is `local`. |
| `LOCAL_MODEL` | `qwen2.5-coder:7b` | The local model to grade with. |
| `SECRET_KEY` | — | **Change it.** Signs JWTs. |
| `DATABASE_URL` | `sqlite:///./autograde.db` | Use PostgreSQL in production. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 8 hours. |
| `UPLOAD_DIR` | `./uploads` | Student files. Back this up. |
| `MAX_FILE_SIZE_MB` | `50` | Enforced while streaming, before the file lands. |
| `CANVAS_BASE_URL` / `CANVAS_API_TOKEN` | empty | Optional. |

## Limitations

- **Grading is synchronous.** A class of 30 takes a few minutes. There is
  no job queue; the request stays open.
- **No student-facing interface.** This is an instructor tool.
- **Similarity flags are prompts to look, not verdicts.** Two students who
  worked from the same lecture example will legitimately look alike.
- **The model can be wrong.** That is why nothing is final until you say
  so, and why the raw model output is kept for every grade.
