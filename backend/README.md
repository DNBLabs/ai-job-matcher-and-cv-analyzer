# AI Job Matcher — Backend

FastAPI API and Analysis Run worker. See repository root `docker-compose.yml` for local development (Postgres, Azurite, RabbitMQ).

```bash
pip install -e ".[dev]"
pytest
pytest tests/ports/    # infrastructure port contract tests
uvicorn app.main:app --reload
python -m worker.main
```

Infrastructure ports (`BlobStore`, `JobQueue`, `SecretProvider`) are wired via `app.adapters.factory` from environment settings. CI defaults use in-memory adapters; Docker Compose selects Azurite + RabbitMQ.
