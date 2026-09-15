@canonical @piclaw-baseline
Feature: Piclaw-compatible interaction model
  Both ports expose the same observable user flows as Piclaw through native UI and APIs.
  Unsupported capabilities fail their tagged scenario rather than being simulated.
  Safety deviations are explicit and require alignment instead of weakening safeguards.

  Background:
    Given an isolated canonical database
    And the canonical current session "main"
    And a second session "research"
    And deterministic native assets and registry data
    And all actions are performed through visible enabled controls

  @shell @pointer @keyboard
  Scenario Outline: Open and dismiss the workspace menu
    Given the workspace menu is closed
    When I open the workspace menu using <input>
    Then the workspace menu is open exactly once
    And focus can reach each enabled menu item
    When I dismiss the workspace menu using <dismissal>
    Then the workspace menu is closed
    And no underlying control is activated
    And focus returns to a usable shell control

    Examples:
      | input    | dismissal      |
      | pointer  | outside pointer|
      | keyboard | Escape         |

  @shell @workspace @responsive
  Scenario: Show and hide the native workspace
    Given the composer contains canonical unsent content
    When I choose "Show workspace" from the workspace menu
    Then the native workspace tree is visible
    And the workspace menu is closed
    When I hide the workspace
    Then the current session and composer content are unchanged
    And on narrow layouts the drawer backdrop activates no Plan or composer control

  @quick-actions @typeahead @keyboard
  Scenario: Type on the idle timeline to open Quick actions
    Given focus is on noninteractive timeline content
    And no modal, session picker, model picker, workspace editor or composer control is active
    When I type one printable non-whitespace character without Control, Meta or Alt
    Then Quick actions opens exactly once
    And its search field has focus
    And the typed character is the initial query
    And matching sessions, workspace actions and supported slash commands are grouped in native order
    And the highlighted result prefers exact title, then title prefix, then the first result
    When I press ArrowDown or ArrowUp
    Then the highlight wraps through the filtered results
    When I press Enter
    Then the highlighted action runs exactly once
    And Quick actions closes without erasing the composer draft

  @quick-actions @typeahead @focus @failure
  Scenario Outline: Do not steal typing from an interactive surface
    Given focus is inside <surface>
    When I type a printable character
    Then Quick actions remains closed
    And the surface receives the character normally

    Examples:
      | surface                  |
      | composer textarea        |
      | input or select          |
      | button or link           |
      | contenteditable editor   |
      | workspace sidebar        |
      | open modal dialog        |
      | session or model picker  |

  @quick-actions @typeahead @ime
  Scenario: Ignore consumed, modified and composing keys
    Given focus is on noninteractive timeline content
    When a key event is already prevented, repeated, composing, whitespace, Control-modified, Meta-modified or Alt-modified
    Then Quick actions remains closed
    And no action is activated

  @quick-actions @dismissal @scope
  Scenario Outline: Dismiss Quick actions without side effects
    Given Quick actions was opened from a connected visible trigger
    And its search query has not activated an action
    When I dismiss it using <dismissal>
    Then Quick actions is closed
    And focus returns to the connected opening trigger when applicable
    And the current session, composer draft, media and references are unchanged

    Examples:
      | dismissal       |
      | Escape          |
      | outside pointer |
      | close control   |

  @quick-actions @scope @race @failure
  Scenario: Activate only current supported Quick actions
    Given command and session results are scoped to session "main"
    When I change to session "research" while an older catalogue or activation is pending
    Then the older result cannot replace or activate an action in "research"
    And failed activation keeps Quick actions open with recoverable input and an error
    And unsupported commands and workspace actions are absent rather than simulated
    And command insertion preserves the existing composer draft and does not submit it

  @plan @pointer @keyboard
  Scenario Outline: Open Plan and edit the loaded revision
    Given session "main" has the canonical Plan at revision 1
    When I open Plan using <input>
    Then its editor and real checklist progress are visible
    When I edit the Plan and save revision 1
    Then the native Plan tool reads the saved text at revision 2
    And a reload preserves that text and revision

    Examples:
      | input    |
      | pointer  |
      | keyboard |

  @plan @race @failure
  Scenario: Preserve a dirty Plan across a remote update
    Given the open Plan editor has unsaved local text
    When the native Plan tool writes different text with the loaded revision
    Then the remote text is stored and emits a session-scoped update
    And the editor retains its local text
    And the UI reports that refresh is required
    When I refresh the dirty Plan
    Then I must confirm before discarding local text

  @plan @scope @submit
  Scenario: Submit Plan to the captured session
    Given Plan and composer both contain unsent content
    When I choose "Submit to model"
    Then Plan is saved before it is sent
    And normal send or queue policy targets session "main"
    And composer text, media and references remain unchanged
    And switching sessions cannot retarget the pending submission

  @session-picker @pointer @keyboard
  Scenario Outline: Open, search and dismiss the session picker
    When I open the session picker using <input>
    Then search has focus before the first visible paint
    And the popup remains anchored to its native composer target
    And sessions "main" and "research" are present by native identifier
    When I dismiss it with Escape
    Then no session changes
    And focus returns to the session-picker trigger

    Examples:
      | input    |
      | pointer  |
      | keyboard |

  @session-picker @scope @race
  Scenario: Select one coherent session view
    Given delayed responses exist for session "main"
    When I select session "research" using keyboard navigation
    Then timeline, queue, model, context and composer all show "research"
    And a late "main" response replaces none of them

  @session-picker @capability
  Scenario: Expose only supported session mutations
    Then pin, archive, restore, rename, delete and child-session creation are enabled only when implemented by the native API
    And running or unknown-count sessions cannot be deleted
    And a failed mutation keeps the picker and selection recoverable

  @queue @fifo
  Scenario: Queue two follow-ups exactly once
    Given session "main" has an active turn
    When I send two canonical follow-ups
    Then both native queue IDs are visible in FIFO order
    And their text, media and references are stored once
    And session "research" is unchanged

  @queue @return @race @failure
  Scenario: Return a queued item to the latest editor draft
    Given the composer draft changes while return-to-editor is pending
    When I return the selected queue item to the editor
    Then its recovery record and merged origin-session draft persist before DELETE
    And the latest concurrent draft text is retained
    And media and references are retained
    And retrying a partial failure creates no duplicate
    And a storage failure prevents DELETE

  @queue @remove @reorder @scope
  Scenario: Reorder and remove by durable identity
    When I move one queued item by one adjacent position
    Then only that target group's persisted FIFO order changes
    When native removal rejects the selected queue ID
    Then the selected row remains or reconciles to authoritative consumed state
    And no other session or composer draft changes

  @queue @steer @safety-deviation
  Scenario: Steer only a matching active run
    Given activity is idle or unknown
    Then Steer is disabled and sends no request
    Given session "main" has a matching active run and queued item
    When I activate Steer twice
    Then the original queued ID is consumed at most once
    And delivery targets only that run and session
    And failure leaves the item queued
    # Piclaw currently enables idle Steer. Both ports must converge on this safer outcome;
    # visual equality must not be achieved by enabling an unsafe action.

  @model-picker @pointer @keyboard
  Scenario Outline: Search and select a model authoritatively
    Given two real registry models with explicit capabilities
    And the composer has unsent text and references
    When I open the model picker using <input>
    And I search for and select the second model
    Then the accepted native mutation updates the session model and context window
    And reload preserves the selected model only for session "main"
    And composer content is unchanged

    Examples:
      | input    |
      | pointer  |
      | keyboard |

  @model-picker @failure @race @truthful-ui
  Scenario: Reject stale or unsupported model state
    Given a model switch is pending for session "main"
    When I switch to session "research"
    Then the late response cannot change the "research" model label
    And a rejected switch retains the prior model and composer draft
    And thinking appears only for advertised support
    And unknown context remains unavailable
    And local token estimates are labelled estimates
    And compaction is actionable only when natively supported

  @turn @reconnect @scope
  Scenario: Cancel the captured active turn across reconnect
    Given a busy turn has captured session, turn and runtime owner
    When SSE disconnects and reconnects
    Then busy state is refreshed without changing ownership
    When I activate the distinct stop control
    Then only that captured turn is cancelled
    And composer and queue are preserved
    And a stale terminal event cannot stop a newer turn

  @attachments @failure
  Scenario: Retry attachment delivery without duplication
    Given upload or paste shows one native progress control
    When I cancel and retry the selected file
    Then cancellation prevents send and retains the draft
    And retry delivers one durable media item to the active destination
    And it survives reload and source removal

  @copy @speech @capability
  Scenario: Copy and read assistant content truthfully
    When I copy an assistant code block
    Then the clipboard receives original stored text rather than highlighted HTML
    And read aloud is shown only when the browser and assistant text support it
    And starting another post transfers speech ownership
    And stale completion callbacks do nothing
