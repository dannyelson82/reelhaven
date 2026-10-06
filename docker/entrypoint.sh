#!/bin/sh
# Container entrypoint (ARCHITECTURE.md §5.4): starts as root only to apply
# PUID/PGID/UMASK and GPU device groups, then drops privileges for good.
set -eu

PUID="${PUID:-99}"
PGID="${PGID:-100}"
UMASK="${UMASK:-022}"

case "$PUID$PGID" in
  *[!0-9]*) echo "PUID and PGID must be numbers" >&2; exit 1 ;;
esac
case "$UMASK" in
  *[!0-7]*) echo "UMASK must be an octal number such as 022" >&2; exit 1 ;;
esac

if [ "$(id -u)" = "0" ]; then
  if [ "$PUID" = "0" ]; then
    echo "Refusing to run as root (PUID=0). Use Unraid's default PUID=99 PGID=100." >&2
    exit 1
  fi
  groupmod --non-unique --gid "$PGID" reelhaven
  usermod --non-unique --uid "$PUID" --gid "$PGID" reelhaven

  # GPU access for Intel/AMD: join whatever groups own the passed-in devices.
  for dev in /dev/dri/renderD* /dev/dri/card*; do
    [ -e "$dev" ] || continue
    gid="$(stat -c %g "$dev")"
    [ "$gid" = "0" ] && continue
    group="$(getent group "$gid" | cut -d: -f1 || true)"
    if [ -z "$group" ]; then
      group="gpu$gid"
      groupadd --gid "$gid" "$group"
    fi
    usermod --append --groups "$group" reelhaven
  done

  # Only ReelHaven's own folders, never the media library. /config is fixed
  # recursively only when PUID changed (it holds just the database and logs).
  if [ "$(stat -c %u /config)" != "$PUID" ]; then
    chown -R "$PUID:$PGID" /config
  fi
  chown "$PUID:$PGID" /transcode
  umask "$UMASK"
  exec setpriv --reuid="$PUID" --regid="$PGID" --init-groups --inh-caps=-all \
    --no-new-privs "$@"
fi

umask "$UMASK"
exec "$@"
