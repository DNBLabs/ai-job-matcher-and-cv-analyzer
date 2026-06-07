# AI Job Matcher — Backend

FastAPI API and Analysis Run worker. See repository root `docker-compose.yml` for local development (Postgres, Azurite, RabbitMQ).

```bash
pip install -e ".[dev]"
pytest
pytest tests/domain/   # domain logic + repository behavior tests
pytest tests/ports/    # infrastructure port contract tests
pytest tests/auth/     # session store + auth dependency tests (Task 3)
uvicorn app.main:app --reload
python -m worker.main
```

## Database migrations

Uses Alembic with SQLAlchemy 2.0 ORM (`postgresql+psycopg://` driver).
Source: https://alembic.sqlalchemy.org/en/latest/tutorial.html#running-our-first-migration

```bash
# With Compose Postgres running on 127.0.0.1:5432
alembic upgrade head
ADMIN_EMAIL=you@example.com python -m scripts.seed_admin
```

CI runs `pytest tests/ports/`, `pytest tests/domain/`, `pytest tests/auth/`, `alembic upgrade head`, `pytest tests/auth/test_sessions_postgres.py`, then the full suite against an ephemeral Postgres 16 service container on every PR.
Source: https://docs.github.com/en/actions/using-containerized-services/creating-postgresql-service-containers

Infrastructure ports (`BlobStore`, `JobQueue`, `SecretProvider`) are wired via `app.adapters.factory` from environment settings. CI defaults use in-memory adapters; Docker Compose selects Azurite + RabbitMQ.
