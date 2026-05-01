Feature: API Health and Endpoints
  As a developer
  I want the backend API endpoints to be accessible
  So that the frontend can communicate with the server

  Scenario: Health endpoint returns ok
    When I request GET "/health"
    Then the response status should be 200
    And the response body should contain "ok"

  Scenario: Agents endpoint returns a list
    When I request GET "/agents"
    Then the response status should be 200
    And the response body should be a JSON array

  Scenario: Timeline endpoint returns posts
    When I request GET "/timeline"
    Then the response status should be 200
    And the response body should have property "posts"

  Scenario: SSE stream endpoint connects
    When I request GET "/sse/stream"
    Then the response status should be 200
    And the response content-type should contain "text/event-stream"

  Scenario: Agent commands endpoint returns commands
    When I request GET "/agent/commands"
    Then the response status should be 200
    And the response body should be a JSON array

  Scenario: Agent status endpoint returns state
    When I request GET "/agent/status"
    Then the response status should be 200

  Scenario: Workspace tree endpoint returns entries
    When I request GET "/workspace/tree"
    Then the response status should be 200
    And the response body should have property "entries"

  Scenario: Search endpoint requires query parameter
    When I request GET "/search"
    Then the response status should be 400
