#!/bin/sh
# Starts the API as an unprivileged user.
#
# The container is built to run as `app` (uid 10001). If it is started as root (the default for
# `docker run`/Compose) this script first repairs ownership of the data directories, then drops
# to `app`. That matters when upgrading: volumes created by the old root-running image hold
# root-owned files the unprivileged user could otherwise not write. When the platform already
# starts the container as a non-root user (Kubernetes runAsUser, `user:` in Compose) it just execs.
#
# Rootless Podman has two distinct volume-permission cases, and only one of them is the "no extra
# handling needed" case:
#
#   - Default rootless Podman (no --userns given): the container still starts as uid 0 *inside its
#     own user namespace*, so the root branch below runs exactly as it does under Docker. The
#     chown/stat calls only ever see and touch the namespace-local UID/GID; Podman's own
#     /etc/subuid + /etc/subgid remapping to real host UIDs happens transparently beneath that
#     namespace and this script never needs to know it exists.
#   - `podman run --userns=keep-id` (common specifically so a bind-mounted host directory's
#     ownership matches 1:1 between host and container): the container starts directly as the
#     *host* uid, which is essentially never 10001, so `id -u` is already non-zero and the whole
#     ownership-repair branch is skipped — this script used to just exec into the app at that
#     point and let it fail deep inside Python's own startup validation if the mounted directory
#     wasn't already owned by that uid. It now checks writability itself first and fails fast with
#     a message that actually points at the cause.
#
# Podman also has a `:U` volume mount option that does a similar chown from the host side, but
# don't reach for it as a substitute for either case above: it isn't supported inside a compose
# file by podman-compose (only by `podman run` directly), and it would be redundant with the root
# branch's own chown on every other platform this same image runs on.
set -e

APP_UID=10001
APP_GID=10001

dirs="${UPLOAD_DIR:-/app/uploads} /app/data"
case "${DATABASE_URL:-}" in
    sqlite:///*) dirs="$dirs $(dirname "${DATABASE_URL#sqlite:///}")" ;;
esac

if [ "$(id -u)" = "0" ]; then
    for dir in $dirs; do
        mkdir -p "$dir"
        # Only walk the tree when the top directory is wrong; afterwards this is a single stat.
        if [ "$(stat -c %u "$dir")" != "$APP_UID" ]; then
            if ! chown -R "$APP_UID:$APP_GID" "$dir"; then
                echo "ERROR: could not chown '$dir' to $APP_UID:$APP_GID." >&2
                echo "Under rootless Podman, this container's uid 0 is itself mapped to an" >&2
                echo "unprivileged host uid via /etc/subuid, and that mapping's range must be wide" >&2
                echo "enough to cover $APP_UID:$APP_GID. Check 'podman info --format" >&2
                echo "{{.Host.IDMappings}}' on the host, or the invoking user's /etc/subuid and" >&2
                echo "/etc/subgid entries." >&2
                exit 1
            fi
        fi
    done
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --no-new-privs "$@"
fi

# Already non-root (Kubernetes runAsUser, Compose `user:`, or `podman run --userns=keep-id`,
# where the container starts directly as the host's own uid instead of a remapped root). There is
# no privilege left here to fix ownership, so a bind mount that doesn't already belong to this
# uid is a hard failure — check for that now, with a message pointing at the actual cause, rather
# than letting the app fail on its own first write deep inside application startup.
for dir in $dirs; do
    mkdir -p "$dir" 2>/dev/null || true
    if [ ! -w "$dir" ]; then
        echo "ERROR: '$dir' is not writable by uid $(id -u) (this container was already started" >&2
        echo "as a non-root user, so no ownership repair could be attempted)." >&2
        echo "If this is rootless Podman with --userns=keep-id, the mounted host directory's" >&2
        echo "owner must match this container's uid ($(id -u)) directly, e.g.:" >&2
        echo "  podman unshare chown -R $(id -u):$(id -g) <host-directory>" >&2
        echo "Otherwise, drop --userns=keep-id (or the runAsUser/user: override) and let the" >&2
        echo "container start as root instead, so this script's own chown step can fix it." >&2
        exit 1
    fi
done

exec "$@"
