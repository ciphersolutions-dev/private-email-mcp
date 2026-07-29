@smoke
Feature: MCP surface inventory
  As a Claude Code user
  The PrivateEmail MCP server must expose the documented tools, resources, and prompts
  So agents can discover the full mailbox surface

  Scenario: Documented tools are registered
    When the MCP tool inventory is inspected
    Then these tools are registered:
      | health_check        |
      | account_info        |
      | list_folders        |
      | list_emails         |
      | search_emails       |
      | get_email           |
      | get_thread          |
      | download_attachment |
      | send_email          |
      | reply_email         |
      | forward_email       |
      | save_draft          |
      | list_drafts         |
      | send_draft          |
      | move_email          |
      | copy_email          |
      | delete_email        |
      | mark_email          |
      | create_folder       |
      | rename_folder       |
      | delete_folder       |

  Scenario: Documented prompts are registered
    When the MCP prompt inventory is inspected
    Then these prompts are registered:
      | summarize_inbox |
      | triage_unread   |
      | draft_reply     |
      | compose_email   |
