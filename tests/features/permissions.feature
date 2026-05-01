Feature: Permission and Whitelist Management
  As a user
  I want to manage tool call permissions
  So that I can control which actions the agent can take automatically

  Scenario: List whitelist patterns (empty)
    When I request GET "/agent/whitelist"
    Then the response status should be 200
    And the response body should have property "patterns"

  Scenario: Add a whitelist pattern
    When I add whitelist pattern "Run command"
    Then the response status should be 201
    And the whitelist should contain "Run command"

  Scenario: Remove a whitelist pattern
    Given the whitelist contains "Run command"
    When I remove whitelist pattern "Run command"
    Then the response status should be 204
    And the whitelist should not contain "Run command"

  Scenario: Glob matching works
    Given the whitelist contains "Run *"
    When I request GET "/agent/whitelist"
    Then the whitelist should contain "Run *"
