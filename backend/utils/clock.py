import datetime


def utcnow() -> datetime.datetime:
    """Drop-in replacement for the deprecated datetime.datetime.utcnow().

    Returns the current UTC time as a *naive* datetime, on purpose: every
    DateTime column stores naive UTC (SQLite has no timezone support), and the
    API serializes these values with .isoformat() for the frontend. Returning
    an aware datetime here would change what is stored and add a "+00:00"
    suffix to every timestamp in API responses. This is the replacement the
    Python docs recommend for utcnow(), without the deprecation warning.

    Named clock.py rather than time.py so it can never shadow the stdlib
    `time` module when a script inside utils/ is run directly.
    """
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
