Feature: Timeline and Posts
  As a user
  I want to create, view, and manage posts
  So that I can maintain a conversation history

  Scenario: Create a new post
    When I create a post with content "Hello from BDD"
    Then the response status should be 201
    And the response body should have property "id"

  Scenario: Timeline shows created posts
    Given I have created a post with content "Timeline test post"
    When I request GET "/timeline"
    Then the response body property "posts" should not be empty

  Scenario: Delete a post
    Given I have created a post with content "Delete me"
    When I delete the post
    Then the response status should be 204

  Scenario: Reply to a thread
    Given I have created a post with content "Parent post"
    When I reply to the post with content "Reply post"
    Then the response status should be 201

  Scenario: Get a thread
    Given I have created a post with content "Thread parent"
    And I have replied to the post with content "Thread reply"
    When I request the thread for the parent post
    Then the response body property "posts" should have 2 items

  Scenario: Search posts
    Given I have created a post with content "unique searchable keyword zxcvbn"
    When I search for "zxcvbn"
    Then the response body property "posts" should not be empty
