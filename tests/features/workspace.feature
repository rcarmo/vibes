Feature: Workspace Explorer
  As a user
  I want to browse and manage workspace files
  So that I can view and edit project files alongside the chat

  Scenario: Workspace tree loads files
    When I request GET "/workspace/tree"
    Then the response status should be 200
    And the response body should have property "entries"

  Scenario: Read a workspace file
    Given a file "test-read.txt" exists in the workspace with content "hello world"
    When I request GET "/workspace/file?path=test-read.txt"
    Then the response status should be 200
    And the response body should have property "content"
    And the response body property "content" should equal "hello world"

  Scenario: Create a new file
    When I create a workspace file "test-create.txt" with content "created by test"
    Then the response status should be 201
    And the file "test-create.txt" should exist in the workspace

  Scenario: Update a file
    Given a file "test-update.txt" exists in the workspace with content "original"
    When I update the workspace file "test-update.txt" with content "updated"
    Then the response status should be 200
    And reading "test-update.txt" should return "updated"

  Scenario: Delete a file
    Given a file "test-delete.txt" exists in the workspace with content "delete me"
    When I request DELETE "/workspace/file?path=test-delete.txt"
    Then the response status should be 204

  Scenario: Path traversal is rejected
    When I request GET "/workspace/file?path=../../etc/passwd"
    Then the response status should not be 200
