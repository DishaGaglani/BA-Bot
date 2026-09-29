import os

from slowapi import Limiter
from slowapi.util import get_remote_address

"""Shared rate limiter instance. Lives in its own module (rather than in
app.py) so auth/routes.py and routes/projects.py can import it without a
circular import back into app.py, which imports both of those modules."""

limiter = Limiter(key_func=get_remote_address, headers_enabled=True)

# Overridable per deployment (e.g. a stricter limit behind a WAF, or a looser one for load
# testing) instead of being fixed at whatever value the code happened to ship with.
AUTH_RATE_LIMIT = os.getenv("AUTH_RATE_LIMIT", "5/minute")
