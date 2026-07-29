# PrivateEmail MCP BDD acceptance suite
#
# Scope (strict QA gate for releases):
# - Dependency compatibility with mcp 1.x / FastMCP
# - Configuration validation contracts
# - Agent-facing UID/folder/error mapping
# - Sent-folder APPEND reliability helpers
# - Parsing + prompt payload compactness
# - Outbound/draft safety guards
# - SMTP-then-Sent send contract (mocked)
# - Documented MCP tool/prompt surface
#
# Out of scope here (covered by live mailbox smoke, not CI):
# - Real PrivateEmail IMAP/SMTP round-trips
# - Claude Code UI rendering
# - mcp 2.x migration
