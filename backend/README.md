# AI Job Matcher — Backend

FastAPI API and Analysis Run worker. See repository root `docker-compose.yml` for local development.

```bash
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
python -m worker.main
```
