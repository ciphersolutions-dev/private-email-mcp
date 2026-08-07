#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "Usage: $0 <email> <password> <display-name> [scope]" >&2
  echo "Example: $0 you@domain.com 'secret' 'Your Name' user" >&2
  exit 1
fi

EMAIL="$1"
PASSWORD="$2"
DISPLAY_NAME="$3"
SCOPE="${4:-user}"
TAG="${PRIVATEEMAIL_MCP_TAG:-v1.1.4}"

if ! command -v claude >/dev/null 2>&1; then
  echo "Error: claude CLI is not installed or not on PATH" >&2
  exit 1
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "Error: uvx is not installed or not on PATH" >&2
  exit 1
fi

# Replace any previous registration so upgrades are deterministic.
claude mcp remove privateemail --scope "$SCOPE" >/dev/null 2>&1 || true

claude mcp add --scope "$SCOPE" \
  --env PRIVATEEMAIL_ADDRESS="$EMAIL" \
  --env PRIVATEEMAIL_PASSWORD="$PASSWORD" \
  --env PRIVATEEMAIL_DISPLAY_NAME="$DISPLAY_NAME" \
  privateemail \
  -- uvx --from "git+https://github.com/ciphersolutions-dev/private-email-mcp@${TAG}" privateemail-mcp

echo "PrivateEmail MCP added to Claude Code with scope: $SCOPE (tag ${TAG})"
echo "Run: claude mcp get privateemail"
echo
echo "If health_check times out on a VPN that blocks IMAP/SMTP ports, use the"
echo "local tunnel wrapper instead of uvx:"
echo "  git clone ... && ./scripts/run-mcp-with-tunnel.sh"
echo "  PRIVATEEMAIL_TUNNEL_SSH=<ssh-host-with-AllowTcpForwarding>"
