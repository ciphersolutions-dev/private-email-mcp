@critical
Feature: Message parsing and prompt payload safety
  As an agent reading PrivateEmail through MCP
  Summaries and prompts must stay compact and useful
  So context windows are not filled with raw HTML

  Scenario: Header-only parse keeps snippet and skips full body
    Given an email with subject "Header only" and body "This body should not be parsed"
    When the message is parsed without body inclusion using snippet "Preview text"
    Then the parsed subject is "Header only"
    And the parsed text body is "Preview text"
    And the parsed HTML body is empty
    And attachments are empty
    And raw headers are empty

  Scenario: HTML converts to readable plain text
    Given HTML content "<p>Hello <b>world</b></p>"
    When HTML is converted to plain text
    Then the plain text contains "Hello"

  Scenario: Prompt payloads trim oversized text bodies
    Given an email detail with a text body of 9000 characters
    When a prompt email payload is built
    Then the prompt text body length is at most 6000 characters
    And the prompt payload omits raw_headers

  Scenario: Prompt payloads prefer text over giant HTML
    Given an email detail with empty text and HTML of 5000 characters
    When a prompt email payload is built
    Then the prompt text body length is at most 2000 characters
