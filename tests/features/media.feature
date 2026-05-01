Feature: Media Upload and Serving
  As a user
  I want to upload and view media files
  So that I can share images and documents in conversations

  Scenario: Upload a text file
    When I upload a file "test.txt" with content "test content"
    Then the response status should be 201
    And the response body should have property "id"
    And the response body should have property "url"

  Scenario: Serve an uploaded file
    Given I have uploaded a file "serve-test.txt" with content "serve me"
    When I request the media URL for the uploaded file
    Then the response status should be 200
    And the response body should equal "serve me"

  Scenario: Media info endpoint
    Given I have uploaded a file "info-test.txt" with content "info content"
    When I request the media info for the uploaded file
    Then the response status should be 200
    And the response body should have property "filename"
