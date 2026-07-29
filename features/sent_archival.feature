@critical
Feature: Reliable Sent-folder archival
  As a PrivateEmail user sending mail through MCP
  Every successful SMTP delivery must leave a Sent copy
  So webmail and agents see the same outbound history

  Scenario: LF-only RFC822 bytes are normalized to CRLF
    Given raw message bytes with LF-only line endings
    When the message is normalized for IMAP APPEND
    Then every line ending is CRLF
    And no bare LF remains

  Scenario: Mixed line endings become CRLF without doubling
    Given raw message bytes with mixed CRLF and LF endings
    When the message is normalized for IMAP APPEND
    Then every line ending is CRLF
    And the normalized message equals the expected CRLF form

  Scenario Outline: Special-use mailboxes are quoted for Open-Xchange
    When mailbox "<name>" is quoted for APPEND
    Then the quoted mailbox is "<quoted>"

    Examples:
      | name    | quoted    |
      | Sent    | "Sent"    |
      | Drafts  | "Drafts"  |
      | Trash   | "Trash"   |
      | INBOX   | "INBOX"   |
      | "Sent"  | "Sent"    |

  Scenario: Sent archive failure after SMTP is mapped as delivered-but-unarchived
    Given a mail failure "Email was delivered via SMTP (message_id=<x>) but saving a copy to the Sent folder failed after retries: timed out" while "send email"
    When the failure is mapped for agents
    Then the agent error contains "archive it in Sent"
    And the agent error contains "Recipients still received it"
