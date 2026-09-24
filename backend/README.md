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

## CI checks (run locally)

Pull requests run `.github/workflows/ci.yml`. To reproduce the backend gates:

```bash
pip install ruff mypy types-requests
ruff check .   # config: ruff.toml (correctness rules only)
mypy .         # config: mypy.ini
```
