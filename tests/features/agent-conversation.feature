Feature: Agent Conversation
  As a user
  I want to send messages and receive agent responses
  So that I can interact with coding agents through the UI

  Scenario: Send a message and receive a response
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "Say hello world and nothing else." in the compose box
    And I press Enter to send
    Then an agent response should appear in the timeline
    And the agent response should contain "hello"

  Scenario: Agent shows status during streaming
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "Count from 1 to 5, one number per line." in the compose box
    And I press Enter to send
    Then the agent status panel should appear
    And I wait for the agent to finish
    And the agent response should contain "1"
    And the agent response should contain "5"

  Scenario: Agent handles simple math
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "What is 2+2? Reply with just the number." in the compose box
    And I press Enter to send
    Then I wait for the agent to finish
    And the agent response should contain "4"
