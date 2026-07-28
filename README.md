# PrivateEmail MCP

PrivateEmail MCP is a Model Context Protocol server for Namecheap PrivateEmail.
It connects to `mail.privateemail.com` over IMAP and SMTP so Claude Code can read inboxes, search mail, draft replies, send messages, manage folders, and work with drafts.

This server is built for the Namecheap email provider called PrivateEmail.
It is session scoped by design. Everything runs while Claude Code is connected to the server. There are no background workers, schedulers, or durable campaign daemons.

## Reliability notes (v1.1.2)

- Each IMAP tool call uses its own short-lived connection instead of one shared mailbox session
- Inbox listings use header and snippet fetches instead of downloading full message bodies
- Tool failures return clearer, agent-friendly error messages for bad UIDs, missing folders, and auth issues
- Prompts such as `draft_reply` send compact email payloads instead of full HTML blobs
- Sent-folder archival no longer uses fragile `aioimaplib` APPEND. After every SMTP send, the server archives a CRLF-normalized copy into `Sent` with stdlib `imaplib`, retries, and fails loudly if the Sent copy cannot be saved

## What it does

- Reads inbox messages, threads, and attachments
- Searches mail by sender, recipient, subject, body text, and date filters
- Sends new emails
- Replies and forwards while preserving thread headers
- Saves and sends drafts
- Moves, copies, deletes, and marks messages
- Creates, renames, and deletes folders
- Exposes inbox context as MCP resources
- Exposes reusable prompts for summarizing inboxes and drafting replies
- Saves sent messages into the `Sent` folder so they appear in PrivateEmail webmail

## Why this exists

Namecheap PrivateEmail does not provide a public API for mailbox automation in the same way many SaaS products do.
The supported integration path is standard email protocols.
This server gives Claude Code a clean MCP interface on top of those protocols.

## Features exposed to Claude Code

### Tools

- `health_check`
- `account_info`
- `list_folders`
- `list_emails`
- `search_emails`
- `get_email`
- `get_thread`
- `download_attachment`
- `send_email`
- `reply_email`
- `forward_email`
- `save_draft`
- `list_drafts`
- `send_draft`
- `move_email`
- `copy_email`
- `delete_email`
- `mark_email`
- `create_folder`
- `rename_folder`
- `delete_folder`

### Resources

- `privateemail://account`
- `privateemail://folders`
- `privateemail://inbox/recent`
- `privateemail://inbox/unread`
- `privateemail://email/{folder}/{uid}`

### Prompts

- `summarize_inbox`
- `triage_unread`
- `draft_reply`
- `compose_email`

## Requirements

- Python 3.11 or newer
- `uv` installed
- A Namecheap PrivateEmail mailbox

## Installation for Claude Code

### Fastest install from GitHub

After this repository is pushed, add it directly to Claude Code with one command:

```bash
claude mcp add --scope user \
  --env PRIVATEEMAIL_ADDRESS="you@yourdomain.com" \
  --env PRIVATEEMAIL_PASSWORD="your-password" \
  --env PRIVATEEMAIL_DISPLAY_NAME="Your Name" \
  privateemail \
  -- uvx --from git+https://github.com/ciphersolutions-dev/private-email-mcp privateemail-mcp
```

Notes:

- `--scope user` installs it once for all your projects. Use `--scope project` if you want a repo-local setup instead.
- Everything after the `--` separator is the command Claude Code runs.
- `uvx --from git+... privateemail-mcp` installs and launches the server directly from GitHub.

### Install from a local clone

```bash
git clone https://github.com/ciphersolutions-dev/private-email-mcp.git
cd private-email-mcp
uv sync

claude mcp add --scope user \
  --env PRIVATEEMAIL_ADDRESS="you@yourdomain.com" \
  --env PRIVATEEMAIL_PASSWORD="your-password" \
  --env PRIVATEEMAIL_DISPLAY_NAME="Your Name" \
  privateemail \
  -- uv run --directory "$PWD" privateemail-mcp
```

### Helper install script

You can also use the included helper script after cloning the repo:

```bash
./scripts/install-claude-code.sh "you@yourdomain.com" "your-password" "Your Name"
```

By default it registers the server at user scope. Pass a fourth argument of `project` to make it project scoped:

```bash
./scripts/install-claude-code.sh "you@yourdomain.com" "your-password" "Your Name" project
```

## Configuration

Environment variables:

- `PRIVATEEMAIL_ADDRESS` - full mailbox address
- `PRIVATEEMAIL_PASSWORD` - mailbox password
- `PRIVATEEMAIL_DISPLAY_NAME` - display name used for outbound mail
- `PRIVATEEMAIL_IMAP_HOST` - defaults to `mail.privateemail.com`
- `PRIVATEEMAIL_IMAP_PORT` - defaults to `993`
- `PRIVATEEMAIL_SMTP_HOST` - defaults to `mail.privateemail.com`
- `PRIVATEEMAIL_SMTP_PORT` - defaults to `465`
- `PRIVATEEMAIL_MAX_ATTACHMENT_BYTES` - maximum attachment payload returned by the server

Example `.env`:

```bash
PRIVATEEMAIL_ADDRESS=you@yourdomain.com
PRIVATEEMAIL_PASSWORD=your-password
PRIVATEEMAIL_IMAP_HOST=mail.privateemail.com
PRIVATEEMAIL_IMAP_PORT=993
PRIVATEEMAIL_SMTP_HOST=mail.privateemail.com
PRIVATEEMAIL_SMTP_PORT=465
PRIVATEEMAIL_DISPLAY_NAME=Your Name
PRIVATEEMAIL_MAX_ATTACHMENT_BYTES=10485760
```

## Usage in Claude Code

Useful Claude Code commands:

- `claude mcp list`
- `claude mcp get privateemail`
- `claude mcp remove privateemail`

Typical flows:

- Read inbox: use `privateemail://inbox/recent` or call `list_emails`
- Review unread mail: use `triage_unread`
- Draft a reply: use `draft_reply`
- Send a message now: use `send_email`
- Reply in-thread: use `reply_email`
- Save a draft: use `save_draft`

## Development

```bash
uv sync
uv run pytest tests/ -q
```

Run locally:

```bash
uv run privateemail-mcp
```

## PrivateEmail behavior note

SMTP delivery alone does not create a copy in the `Sent` folder.
This server explicitly appends a copy to `Sent` after a successful send so the message shows up in PrivateEmail webmail.

## Security

- Keep your mailbox password in environment variables, not source control
- `.env` is ignored by git
- Consider using a dedicated mailbox or app-specific credential if your setup allows it

## License

MIT
