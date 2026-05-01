Feature: Slash Commands
  As a user
  I want to use slash commands for quick actions
  So that I can control the agent and system without leaving the chat

  Scenario: Slash autocomplete appears when typing /
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "/" in the compose box
    Then the slash autocomplete dropdown should be visible

  Scenario: /commands lists available commands
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "/commands" in the compose box
    And I press Enter to send
    Then an agent response should appear in the timeline

  Scenario: /clear command is recognized
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "/clear" in the compose box
    And I press Enter to send
    Then the system should acknowledge the command
