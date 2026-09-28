# ---- Stage 1: build the Python environment -----------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt


# ---- Stage 2: minimal runtime image ------------------------------------------------------
# Only the finished virtualenv is copied over: no compiler, no pip cache, no build tools.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/app \
    UPLOAD_DIR=/app/uploads

# Unprivileged account the API runs as (see docker-entrypoint.sh).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

# /app itself must be writable by `app`: the admin panel persists system_settings.json and
# role_permissions.json next to the code. Data directories are the volume mount points.
RUN chown app:app /app \
    && mkdir -p /app/uploads /app/data \
    && chown -R app:app /app/uploads /app/data \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# NOTE for anyone running this image directly (docker-compose.yml already sets this up):
# --cap-drop ALL --cap-add CHOWN --cap-add SETUID --cap-add SETGID is the intended baseline
# (chown for the entrypoint's ownership repair, setuid/setgid to drop to `app`). If you also
# pass --init (recommended, reaps zombie processes), add --cap-add KILL as well: the init
# process (tini) runs as root and forwards docker stop's SIGTERM to gunicorn by calling
# kill(), which needs CAP_KILL even for root once capabilities are dropped. Without it,
# `docker stop`/`docker compose stop` cannot deliver the signal, so gunicorn's graceful
# shutdown (finish in-flight requests, see gunicorn.conf.py's graceful_timeout) never runs
# and the container just hangs until the stop timeout forcibly kills it instead.

# Liveness only (no dependencies): used by `docker ps`, Compose and Swarm. Kubernetes ignores
# this and should probe /health/live and /health/ready directly.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health/live' % os.getenv('PORT', '8000'), timeout=4)"]

# Starts as root only long enough to fix volume ownership, then runs everything as `app`.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
