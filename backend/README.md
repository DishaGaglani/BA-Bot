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
