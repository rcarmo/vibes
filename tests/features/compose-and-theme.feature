Feature: Compose Box UX
  As a user
  I want the compose box to be responsive and feature-rich
  So that I can efficiently write and send messages

  Scenario: Enter sends message, Shift+Enter inserts newline
    Given I navigate to the app
    And I wait for the SSE connection
    When I type "Line one" in the compose box
    And I press Shift+Enter
    And I type "Line two" in the compose box
    Then the compose textarea should contain a newline

  Scenario: Compose history with arrow keys
    Given I navigate to the app
    And I wait for the SSE connection
    And I have sent the message "First test message"
    And I wait for the agent to finish
    And I have sent the message "Second test message"
    And I wait for the agent to finish
    When I press ArrowUp in the compose box
    Then the compose textarea should not be empty

  Scenario: Model picker typeahead
    Given I navigate to the app
    And I wait for the SSE connection
    When I open the model picker
    And I type "gpt" without focusing the textarea
    Then the model picker should highlight a matching model

Feature: Theme Support
  As a user
  I want the app to respect my color scheme preference
  So that it's comfortable to use in any lighting

  Scenario: Dark mode renders correctly
    Given I set the color scheme to "dark"
    When I navigate to the app
    Then the page background should be a dark color

  Scenario: Light mode renders correctly
    Given I set the color scheme to "light"
    When I navigate to the app
    Then the page background should be a light color
