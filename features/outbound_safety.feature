@critical
Feature: Outbound composition and draft safety
  As an agent composing or sending PrivateEmail messages
  Outbound MIME and draft sends must reject unsafe empties
  So SMTP never receives blank recipients or silent no-ops

  Scenario: Built messages include display name and plain body
    Given a composed message from "a@b.com" as "Ann" to "c@d.com" with subject "Hi" and text "Body"
    Then the MIME subject is "Hi"
    And the MIME From contains "Ann"
    And the MIME plain body is "Body"

  Scenario: Reply subject gains Re: prefix once
    Given an original subject "Hello"
    When a reply subject is prepared
    Then the reply subject is "Re: Hello"

  Scenario: Existing Re: prefix is not duplicated
    Given an original subject "Re: Hello"
    When a reply subject is prepared
    Then the reply subject is "Re: Hello"

  Scenario: Forward subject gains Fwd: prefix once
    Given an original subject "Hello"
    When a forward subject is prepared
    Then the forward subject is "Fwd: Hello"

  Scenario: Attachment helper rejects missing files
    When attachment paths " /tmp/privateemail-mcp-missing-file.bin " are resolved
    Then an attachment error mentions "does not exist"

  Scenario: send_draft rejects drafts with no recipients
    Given a draft email detail with no To recipients and body "Hi"
    When send_draft preconditions are checked
    Then a draft send error mentions "no To recipients"

  Scenario: send_draft rejects drafts with empty bodies
    Given a draft email detail to "a@b.com" with empty body
    When send_draft preconditions are checked
    Then a draft send error mentions "empty body"
