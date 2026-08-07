Feature: Network timeouts and SSH tunnel connectivity
  As an agent using PrivateEmail MCP on a VPN that blocks mail ports
  I need fast failures and a documented tunnel path
  So tools stop hanging for a minute and become usable again

  Scenario: Connect timeout defaults are fail-fast
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    And PRIVATEEMAIL_PASSWORD is "secret"
    When configuration is loaded
    Then the connect timeout is 12 seconds
    And the command timeout is 30 seconds

  Scenario: Loopback IMAP host defaults TLS hostname to PrivateEmail
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    And PRIVATEEMAIL_PASSWORD is "secret"
    And PRIVATEEMAIL_IMAP_HOST is "127.0.0.1"
    And PRIVATEEMAIL_IMAP_PORT is "21993"
    When configuration is loaded
    Then the resolved IMAP TLS hostname is "mail.privateemail.com"

  Scenario: Explicit TLS hostname is preserved
    Given PrivateEmail env is cleared
    And PRIVATEEMAIL_ADDRESS is "user@example.com"
    And PRIVATEEMAIL_PASSWORD is "secret"
    And PRIVATEEMAIL_IMAP_HOST is "127.0.0.1"
    And PRIVATEEMAIL_TLS_HOSTNAME is "mail.privateemail.com"
    When configuration is loaded
    Then the resolved IMAP TLS hostname is "mail.privateemail.com"

  Scenario: Direct-connect timeout maps to VPN/firewall guidance
    Given a mail failure "timed out" while "list folders"
    And the IMAP host is "mail.privateemail.com"
    When the failure is mapped for agents
    Then the agent error contains "could not connect"
    And the agent error contains "mail-tunnel.sh"

  Scenario: Tunnel timeout tells the agent to restart the forward
    Given a mail failure "timed out" while "list folders"
    And the IMAP host is "127.0.0.1"
    When the failure is mapped for agents
    Then the agent error contains "tunnel"
    And the agent error contains "mail-tunnel.sh"
