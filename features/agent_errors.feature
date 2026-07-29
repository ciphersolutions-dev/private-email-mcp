@critical
Feature: Agent-facing input and error contracts
  As an AI agent calling PrivateEmail tools
  I need deterministic validation and readable errors
  So I can recover without guessing IMAP protocol details

  Scenario Outline: Invalid IMAP UIDs are rejected before network I/O
    When UID "<uid>" is validated
    Then validation fails with "Invalid IMAP UID"

    Examples:
      | uid  |
      | abc  |
      | 12.3 |
      | 1 2  |

  Scenario: Empty UID is rejected
    When an empty UID is validated
    Then validation fails with "Invalid IMAP UID"

  Scenario: Valid numeric UIDs are accepted
    When UID "42" is validated
    Then validation succeeds with value "42"

  Scenario: Empty folder names are rejected
    When an empty folder is validated
    Then validation fails with "Folder name is required"

  Scenario Outline: Mail errors map to actionable ToolError messages
    Given a mail failure "<raw>" while "<action>"
    When the failure is mapped for agents
    Then the agent error contains "<needle>"

    Examples:
      | raw                                                                 | action       | needle                          |
      | LOGIN failed: authentication failed                                 | list emails  | authentication failed           |
      | SELECT Missing failed: NO                                           | list emails  | Folder not found                |
      | command illegal in state AUTH                                       | search emails| IMAP state error                |
      | timed out waiting for response                                      | list emails  | timed out                       |
      | FETCH 99 failed: NO                                                 | get email    | Could not read the requested    |
      | Email was delivered via SMTP (message_id=<x>) but saving a copy to the Sent folder failed after retries: timed out | send email | archive it in Sent |
