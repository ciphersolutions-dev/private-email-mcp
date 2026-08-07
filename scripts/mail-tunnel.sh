#!/usr/bin/env bash
# SSH LocalForward so PrivateEmail MCP works when the local network/VPN
# blackholes outbound IMAP(993)/SMTP(465).
#
# Usage:
#   ./scripts/mail-tunnel.sh              # foreground
#   ./scripts/mail-tunnel.sh --daemon     # background, writes PID file
#   ./scripts/mail-tunnel.sh --stop
#
# Then point the MCP at the tunnel:
#   PRIVATEEMAIL_IMAP_HOST=127.0.0.1
#   PRIVATEEMAIL_IMAP_PORT=21993
#   PRIVATEEMAIL_SMTP_HOST=127.0.0.1
#   PRIVATEEMAIL_SMTP_PORT=21465
#   PRIVATEEMAIL_TLS_HOSTNAME=mail.privateemail.com
set -euo pipefail

# Default to ubee: ciphersolutions has AllowTcpForwarding no.
SSH_HOST="${PRIVATEEMAIL_TUNNEL_SSH:-ubee}"
IMAP_LOCAL="${PRIVATEEMAIL_TUNNEL_IMAP_PORT:-21993}"
SMTP_LOCAL="${PRIVATEEMAIL_TUNNEL_SMTP_PORT:-21465}"
REMOTE_HOST="${PRIVATEEMAIL_TUNNEL_REMOTE_HOST:-mail.privateemail.com}"
PID_FILE="${PRIVATEEMAIL_TUNNEL_PID_FILE:-${XDG_RUNTIME_DIR:-/tmp}/privateemail-mail-tunnel.pid}"

start_foreground() {
  echo "Forwarding 127.0.0.1:${IMAP_LOCAL}->${REMOTE_HOST}:993 and 127.0.0.1:${SMTP_LOCAL}->${REMOTE_HOST}:465 via ${SSH_HOST}"
  exec ssh -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${IMAP_LOCAL}:${REMOTE_HOST}:993" \
    -L "127.0.0.1:${SMTP_LOCAL}:${REMOTE_HOST}:465" \
    "${SSH_HOST}"
}

start_daemon() {
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "Tunnel already running (pid $(cat "${PID_FILE}"))"
    exit 0
  fi
  ssh -N -f \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -L "127.0.0.1:${IMAP_LOCAL}:${REMOTE_HOST}:993" \
    -L "127.0.0.1:${SMTP_LOCAL}:${REMOTE_HOST}:465" \
    "${SSH_HOST}"
  # Best-effort PID discovery for this forward.
  sleep 0.3
  pgrep -f "ssh -N -f .*${IMAP_LOCAL}:${REMOTE_HOST}:993" | head -n1 >"${PID_FILE}" || true
  echo "Tunnel started via ${SSH_HOST} (pid file ${PID_FILE})"
}

stop_daemon() {
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}")"
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}"
      echo "Stopped tunnel pid ${pid}"
    fi
    rm -f "${PID_FILE}"
  fi
  # Also clear any matching leftover forwards.
  pkill -f "ssh -N .*${IMAP_LOCAL}:${REMOTE_HOST}:993" 2>/dev/null || true
}

case "${1:-}" in
  --daemon|-d) start_daemon ;;
  --stop) stop_daemon ;;
  --help|-h)
    sed -n '2,16p' "$0"
    ;;
  *) start_foreground ;;
esac
