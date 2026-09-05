# Docker

Three compose files.

| File | For | Guide |
|---|---|---|
| `docker-compose.local.yml` | **What a professor installs** - one computer | [INSTALL.md](../INSTALL.md) |
| `docker-compose.prod.yml` | A department server for many people | [DEPLOYMENT.md](../docs/developer/DEPLOYMENT.md) |
| `docker-compose.yml` | Working on the code | this file |

Two images, both built from the repository root:

| File | Image | Port |
|---|---|---|
| `Dockerfile.backend` | FastAPI + uvicorn, and the grading worker | 8000 |
| `Dockerfile.frontend` | Streamlit | 8501 |

## Run the development stack

```bash
cp .env.example .env
```

Fill in `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) and `SECRET_KEY`, then:

```bash
docker compose up --build
```

- App: <http://localhost:8501>
- API docs: <http://localhost:8000/docs>

Three services start: `backend`, `worker`, `frontend`. **`worker` is the one that grades.** Without it, jobs are accepted and then sit at `queued`.

The frontend reaches the backend at `http://backend:8000` over the compose network; `AUTOGRADE_API_BASE` is set for you.

## With PostgreSQL

SQLite is the default and is fine for a single course. For anything shared, start the `postgres` profile:

```bash
POSTGRES_PASSWORD=a-real-password DATABASE_URL=postgresql://autograde:a-real-password@db:5432/autograde docker compose --profile postgres up --build
```

Then run the migrations once:

```bash
docker compose exec backend alembic upgrade head
```

## Volumes

| Volume | Holds | Losing it means |
|---|---|---|
| `uploads` | student submission files | grades survive; the original files do not |
| `data` | the SQLite database (default profile) | everything is lost |
| `pgdata` | PostgreSQL data (postgres profile) | everything is lost |

Back up `data` (or `pgdata`) before upgrading.

## Notes

- Both images run as an unprivileged user (`autograde`, uid 1000).
- `backend` and `frontend` declare a `HEALTHCHECK`. `worker` does not — it serves no port, and Docker restarts it if it dies.
- `.env` is read at container start. After changing a key:

```bash
docker compose restart backend worker
```

## Production files

| File | Purpose |
|---|---|
| `Caddyfile` | HTTPS termination, security headers, request body limit |
| `entrypoint.sh` | Runs `alembic upgrade head`, then uvicorn |
| `backup.sh` | The nightly `pg_dump` loop |
