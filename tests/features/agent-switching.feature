Feature: Agent Switching
  As a user
  I want to switch between different coding agents
  So that I can use the best agent for each task

  Scenario: List available agents
    When I request GET "/agents"
    Then the response body should be a JSON array
    And each agent should have an "id" and "status" field

  Scenario: Get agent status
    When I request GET "/agent/status"
    Then the response body should have property "status"
    And the response body should have property "agent_id"

  Scenario: Get agent models
    When I request GET "/agent/models"
    Then the response body should have property "current"
    And the response body should have property "models"
