Feature: Link Preview
  As a user
  I want rich link previews for URLs in messages
  So that I can see context without clicking through

  Scenario: Fetch a link preview
    When I request a link preview for "https://example.com"
    Then the response status should be 200
    And the response body should have property "url"
    And the response body should have property "title"
