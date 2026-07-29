@critical @smoke
Feature: MCP SDK dependency compatibility
  As a Claude Code user installing PrivateEmail MCP from GitHub
  I must get a working FastMCP-based server
  So install does not crash on import

  Background:
    Given the published package declares an MCP SDK upper bound below 2.0.0

  @critical
  Scenario: FastMCP import path remains available
    When the privateemail MCP server module is imported
    Then the FastMCP server object is available
    And the installed mcp package major version is 1

  @critical
  Scenario: Package metadata refuses mcp 2.x
    When package metadata for privateemail-mcp is inspected
    Then the mcp dependency constraint includes an upper bound below 2.0.0
