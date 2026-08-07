#!/usr/bin/env bash
# Start (or reuse) the SSH mail tunnel, then run the PrivateEmail MCP server.
# Use this as the Cursor/Claude MCP command when the local VPN blocks mail ports.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PRIVATEEMAIL_TUNNEL_SSH="${PRIVATEEMAIL_TUNNEL_SSH:-ubee}"

"${ROOT}/scripts/mail-tunnel.sh" --daemon

# Prefer tunnel endpoints unless the caller already overrode them.
export PRIVATEEMAIL_IMAP_HOST="${PRIVATEEMAIL_IMAP_HOST:-127.0.0.1}"
export PRIVATEEMAIL_IMAP_PORT="${PRIVATEEMAIL_IMAP_PORT:-21993}"
export PRIVATEEMAIL_SMTP_HOST="${PRIVATEEMAIL_SMTP_HOST:-127.0.0.1}"
export PRIVATEEMAIL_SMTP_PORT="${PRIVATEEMAIL_SMTP_PORT:-21465}"
export PRIVATEEMAIL_TLS_HOSTNAME="${PRIVATEEMAIL_TLS_HOSTNAME:-mail.privateemail.com}"
export PRIVATEEMAIL_CONNECT_TIMEOUT="${PRIVATEEMAIL_CONNECT_TIMEOUT:-12}"
export PRIVATEEMAIL_COMMAND_TIMEOUT="${PRIVATEEMAIL_COMMAND_TIMEOUT:-30}"

cd "${ROOT}"
exec uv run --directory "${ROOT}" privateemail-mcp
