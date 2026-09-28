# Python API backend

This folder contains a minimal FastAPI backend for the BA Bot app.

## Run locally

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open:
- http://127.0.0.1:8000/api/health
- http://127.0.0.1:8000/docs

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
