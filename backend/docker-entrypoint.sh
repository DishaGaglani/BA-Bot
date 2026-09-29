#!/bin/sh
# Starts the API as an unprivileged user.
#
# The container is built to run as `app` (uid 10001). If it is started as root (the default for
# `docker run`/Compose) this script first repairs ownership of the data directories, then drops
# to `app`. That matters when upgrading: volumes created by the old root-running image hold
# root-owned files the unprivileged user could otherwise not write. When the platform already
# starts the container as a non-root user (Kubernetes runAsUser, `user:` in Compose) it just execs.
#
# This is also what makes rootless Podman work without any extra handling: the chown/stat calls
# above run inside the container's own user namespace, so they only ever see and touch the
# namespace-local UID/GID Podman already remapped via /etc/subuid and /etc/subgid on the host — the
# same code path as Docker, no subuid/subgid-aware logic needed here. Podman also has a `:U` volume
# mount option that does this same chown from the host side, but don't reach for it here: it isn't
# supported inside a compose file by podman-compose (only by `podman run` directly), and it would
# be redundant with what this script already does on every start.
set -e

APP_UID=10001
APP_GID=10001

if [ "$(id -u)" = "0" ]; then
    dirs="${UPLOAD_DIR:-/app/uploads} /app/data"
    case "${DATABASE_URL:-}" in
        sqlite:///*) dirs="$dirs $(dirname "${DATABASE_URL#sqlite:///}")" ;;
    esac
    for dir in $dirs; do
        mkdir -p "$dir"
        # Only walk the tree when the top directory is wrong; afterwards this is a single stat.
        if [ "$(stat -c %u "$dir")" != "$APP_UID" ]; then
            chown -R "$APP_UID:$APP_GID" "$dir"
        fi
    done
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --no-new-privs "$@"
fi

exec "$@"
