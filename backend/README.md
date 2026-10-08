# Python API backend

This folder contains the FastAPI backend for the BA Bot app.

## Run locally

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open:
- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/docs

## Run the tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                 # everything (~30s)
pytest -m "not live"   # skip the tests that start a real local server
```

The suite is hermetic: it uses a throwaway database and upload directory, redirects the JSON config files, blocks real
network calls, and stubs the LLM, so it never touches `ba_bot.db` or the Forjinn API.

A test marked `pending_fix(...)` asserts behavior that is only correct once a specific fix is merged. It is expected to
fail until then; when the fix lands it starts passing, pytest reports that as a failure, and the marker should be removed.

## CI checks (run locally)

Pull requests run `.github/workflows/ci.yml`. To reproduce the backend gates:

```bash
pip install ruff mypy types-requests
ruff check .   # config: ruff.toml (correctness rules only)
mypy .         # config: mypy.ini
```

## Database schema changes

Schema is managed by [Alembic](https://alembic.sqlalchemy.org/) (`backend/migrations/`), not hand-written SQL. `app.py` runs pending migrations automatically on startup (`utils/db_bootstrap.py`), so you don't need to run anything by hand for an existing change to take effect.

To make a schema change:
1. Edit the model in `models/models.py`.
2. Generate the migration from that change — never hand-write one:
   ```bash
   alembic revision --autogenerate -m "short description"
   ```
3. Read the generated file under `migrations/versions/` before committing it. Autogenerate detects table/column/index/constraint changes; it does not detect renames (it sees a drop + an add) or write any data migration (backfills, value remaps) — add those by hand only when a change genuinely needs one, in the same revision.
4. Start the app (or run `alembic upgrade head` directly) to apply it locally.

`alembic.ini` has no database URL in it; `migrations/env.py` always reads the same `DATABASE_URL` the app itself uses, so `alembic` targets whichever database you're currently pointed at.
