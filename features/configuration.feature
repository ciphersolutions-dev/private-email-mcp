@critical
Feature: Configuration validation
  As an agent connecting to PrivateEmail
  I need clear configuration failures before any mailbox I/O
  So I can fix env vars instead of chasing opaque IMAP errors

  Scenario: Missing mailbox address is rejected
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_PASSWORD is "secret"
    When configuration is validated
    Then a configuration error mentions "PRIVATEEMAIL_ADDRESS"

  Scenario: Missing mailbox password is rejected
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    When configuration is validated
    Then a configuration error mentions "PRIVATEEMAIL_PASSWORD"

  Scenario: Non-integer IMAP port is rejected
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    And PRIVATEEMAIL_PASSWORD is "secret"
    And PRIVATEEMAIL_IMAP_PORT is "not-a-number"
    When configuration is loaded
    Then a configuration error mentions "PRIVATEEMAIL_IMAP_PORT"

  Scenario: Valid defaults load for PrivateEmail hosts
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    And PRIVATEEMAIL_PASSWORD is "secret"
    When configuration is loaded
    Then the IMAP endpoint is "mail.privateemail.com:993"
    And the SMTP endpoint is "mail.privateemail.com:465"
