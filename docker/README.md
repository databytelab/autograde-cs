# Docker

Two images, both built from the repository root:

| File | Image | Port |
|------|-------|------|
| `Dockerfile.backend`  | FastAPI + uvicorn | 8000 |
| `Dockerfile.frontend` | Streamlit         | 8501 |

## Run the stack

```bash
cp .env.example .env       # then fill in ANTHROPIC_API_KEY and SECRET_KEY
docker compose up --build
```

- API docs: <http://localhost:8000/docs>
- App: <http://localhost:8501>

The frontend reaches the backend at `http://backend:8000` over the compose
network; `AUTOGRADE_API_BASE` is set for you in `docker-compose.yml`.

## With PostgreSQL

SQLite is the default and is fine for a single course. For a shared
deployment, start the `postgres` profile and point the backend at it:

```bash
POSTGRES_PASSWORD=a-real-password \
DATABASE_URL=postgresql://autograde:a-real-password@db:5432/autograde \
docker compose --profile postgres up --build
```

Then run the migrations once:

```bash
docker compose exec backend alembic upgrade head
```

## Volumes

| Volume | Holds | Losing it means |
|--------|-------|-----------------|
| `uploads` | student submission files | grades survive; the original files do not |
| `data`    | the SQLite database (default profile) | everything is lost |
| `pgdata`  | PostgreSQL data (postgres profile) | everything is lost |

Back up `data` (or `pgdata`) before upgrading.

## Notes

- Both images run as an unprivileged user (`autograde`, uid 1000).
- Both declare a `HEALTHCHECK`; the frontend waits for the backend to
  report healthy before it starts.
- `.env` is read at container start. Change a key, then
  `docker compose restart backend`.
