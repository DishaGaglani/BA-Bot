"""Gunicorn settings for the API:  gunicorn -c gunicorn.conf.py app:app

Gunicorn is the process manager (it forks the workers, restarts any that die and does
graceful restarts); each worker is a full Uvicorn ASGI server.

Sizing (override anything with the environment variables shown):
  WEB_CONCURRENCY          number of workers. Default: one per CPU the container may use
                           (read from the cgroup quota), at least 2 so a crashed worker doesn't
                           mean an outage, at most WEB_CONCURRENCY_MAX (4, because the default
                           SQLite database allows one writer at a time), and no more than fits
                           in the memory limit at WORKER_MEMORY_MB (256) each.
  GUNICORN_TIMEOUT         seconds without a heartbeat before a worker is killed (120)
  GUNICORN_GRACEFUL_TIMEOUT  seconds in-flight requests get to finish on restart/stop (60);
                           keep the orchestrator's stop grace period above this
  GUNICORN_MAX_REQUESTS    recycle a worker after this many requests, +/- 10% jitter, to bound
                           slow memory growth from document generation (1000; 0 disables)
  PORT                     listen port (8000)
"""
import math
import os
from typing import Optional

_CGROUP = "/sys/fs/cgroup"


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def cgroup_cpu_limit() -> Optional[float]:
    """CPUs this container may use, from its cgroup quota (v2, then v1); None if unlimited."""
    v2 = _read(f"{_CGROUP}/cpu.max")
    if v2:
        quota, _, period = v2.partition(" ")
        if quota != "max" and period.isdigit() and int(period) > 0:
            return int(quota) / int(period)
        return None
    quota, period = _read(f"{_CGROUP}/cpu/cpu.cfs_quota_us"), _read(f"{_CGROUP}/cpu/cpu.cfs_period_us")
    if quota and period and int(quota) > 0 and int(period) > 0:
        return int(quota) / int(period)
    return None


def cgroup_memory_limit() -> Optional[int]:
    """Memory limit in bytes from the cgroup (v2, then v1); None if unlimited."""
    for path in (f"{_CGROUP}/memory.max", f"{_CGROUP}/memory/memory.limit_in_bytes"):
        value = _read(path)
        if value and value.isdigit() and int(value) < 1 << 60:  # cgroup v1 reports "unlimited" as ~2^63
            return int(value)
    return None


def default_workers(
    cpus: Optional[float] = None,
    memory_bytes: Optional[int] = None,
    *,
    max_workers: int = 4,
    per_worker_mb: int = 256,
) -> int:
    """Worker count for the given CPU and memory budget (None = look it up / unlimited)."""
    cpus = cpus if cpus is not None else (cgroup_cpu_limit() or os.cpu_count() or 1)
    memory_bytes = memory_bytes if memory_bytes is not None else cgroup_memory_limit()
    workers = min(max(math.ceil(cpus), 2), max_workers)
    if memory_bytes:
        workers = min(workers, max(memory_bytes // (per_worker_mb * 1024 * 1024), 1))
    return max(workers, 1)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


bind = f"0.0.0.0:{_int_env('PORT', 8000)}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = _int_env("WEB_CONCURRENCY", 0) or default_workers(
    max_workers=_int_env("WEB_CONCURRENCY_MAX", 4), per_worker_mb=_int_env("WORKER_MEMORY_MB", 256)
)

# Async workers heartbeat from their event loop, so this is not a per-request limit: a long
# LLM stream is fine, a wedged loop is killed.
timeout = _int_env("GUNICORN_TIMEOUT", 120)
graceful_timeout = _int_env("GUNICORN_GRACEFUL_TIMEOUT", 60)
keepalive = 5
max_requests = _int_env("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = max_requests // 10

# Import the app once in the master, then fork. That runs the schema migration and default-user
# seeding a single time, instead of every worker racing to do it on first boot.
preload_app = True
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None  # heartbeat file on tmpfs, not disk

# gunicorn 25+ opens a runtime-management socket under $HOME by default; nothing here uses it.
control_socket_disable = True

# The app writes its own structured request log line; gunicorn's access log would duplicate it.
accesslog = None
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()


def on_starting(server):
    server.log.info(
        "gunicorn: %s workers (cpu limit=%s, memory limit=%s)", workers, cgroup_cpu_limit(), cgroup_memory_limit()
    )


def post_fork(server, worker):
    # Database connections opened in the master while importing the app must not be shared
    # with the workers. close=False drops them without closing the master's copies.
    from database import engine

    engine.dispose(close=False)
