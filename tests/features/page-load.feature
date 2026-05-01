Feature: Page Load and Connection
  As a user
  I want the Vibes app to load and connect to the agent
  So that I can start chatting immediately

  Scenario: SPA loads with correct title
    Given I navigate to the app
    Then the page title should contain "Vibes"

  Scenario: Compose box is visible on load
    Given I navigate to the app
    Then the compose box should be visible
    And the compose textarea should be visible

  Scenario: SSE connection establishes
    Given I navigate to the app
    When I wait for the SSE connection
    Then the compose textarea should be enabled

  Scenario: Timeline area renders
    Given I navigate to the app
    Then the app container should be visible
