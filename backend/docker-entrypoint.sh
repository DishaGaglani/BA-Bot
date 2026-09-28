#!/bin/sh
# Starts the API as an unprivileged user.
#
# The container is built to run as `app` (uid 10001). If it is started as root (the default for
# `docker run`/Compose) this script first repairs ownership of the data directories, then drops
# to `app`. That matters when upgrading: volumes created by the old root-running image hold
# root-owned files the unprivileged user could otherwise not write. When the platform already
# starts the container as a non-root user (Kubernetes runAsUser, `user:` in Compose) it just execs.
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
