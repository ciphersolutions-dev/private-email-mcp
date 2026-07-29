@critical
Feature: SMTP send then Sent archive contract
  As a PrivateEmail MCP sender
  SMTP delivery and Sent APPEND are a single agent-visible transaction
  So agents never assume a Sent copy exists when archival failed

  Scenario: Successful send reports smtp_delivered and saved_to_sent
    Given SMTP delivery will succeed
    And Sent APPEND will succeed on attempt 1
    When an email is sent to "recipient@example.com" with subject "QA ping" and text "hello"
    Then the send result marks smtp_delivered true
    And the send result marks saved_to_sent true
    And the send result includes a message_id

  Scenario: SMTP success with Sent APPEND failure raises a hard error
    Given SMTP delivery will succeed
    And Sent APPEND will fail every attempt
    When an email is sent to "recipient@example.com" with subject "QA ping" and text "hello"
    Then send fails with a message containing "saving a copy to the Sent folder failed"
    And send fails with a message containing "delivered via SMTP"
