import os

from slowapi import Limiter
from slowapi.util import get_remote_address

"""Shared rate limiter instance. Lives in its own module (rather than in
app.py) so auth/routes.py and routes/projects.py can import it without a
circular import back into app.py, which imports both of those modules."""


def get_client_ip(request) -> str:
    """Resolve the per-client key rate limiting buckets on.

    In production this app is only reachable through the bundled Nginx reverse proxy
    (frontend/nginx.conf): the backend container's port is `expose`d, not published, in
    docker-compose.yml, so nothing outside the Docker/Podman network can reach it directly.
    Nginx overwrites X-Forwarded-For with its own view of the real client ($remote_addr)
    rather than appending to whatever the client sent, so this header can't be spoofed by
    the client to evade its own limit or collide with another client's bucket.

    Without this, slowapi's default key_func (get_remote_address) reads the raw socket
    peer address, which behind Nginx/any reverse proxy is always the proxy's own container
    IP for every request — bucketing every distinct client behind the proxy together under
    one shared limit. Falls back to the raw peer address when the header isn't present
    (e.g. running `python app.py` directly, with no reverse proxy in front)."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip, headers_enabled=True)

# Overridable per deployment (e.g. a stricter limit behind a WAF, or a looser one for load
# testing) instead of being fixed at whatever value the code happened to ship with.
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "5/minute")
RATE_LIMIT_PREDICT = os.getenv("RATE_LIMIT_PREDICT", "20/minute")
RATE_LIMIT_EXPORT = os.getenv("RATE_LIMIT_EXPORT", "10/minute")
