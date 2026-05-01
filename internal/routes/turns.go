package routes

import (
	"net/http"
	"sync"

	"github.com/go-chi/chi/v5"
)

// TurnManager tracks active turn content for preview and panel state. (fixes #6)
type TurnManager struct {
	mu     sync.RWMutex
	turns  map[string]*TurnContent
	panels map[string]map[string]bool // turnID -> panelID -> expanded
}

// TurnContent holds accumulated content for an active agent turn.
type TurnContent struct {
	Draft   string `json:"draft,omitempty"`
	Thought string `json:"thought,omitempty"`
	Plan    string `json:"plan,omitempty"`
	Status  string `json:"status,omitempty"`
}

// NewTurnManager creates a new turn manager.
func NewTurnManager() *TurnManager {
	return &TurnManager{
		turns:  make(map[string]*TurnContent),
		panels: make(map[string]map[string]bool),
	}
}

// Update adds content to an active turn.
func (tm *TurnManager) Update(turnID, eventType, text string) {
	tm.mu.Lock()
	defer tm.mu.Unlock()

	tc, ok := tm.turns[turnID]
	if !ok {
		tc = &TurnContent{}
		tm.turns[turnID] = tc
	}

	switch eventType {
	case "draft":
		tc.Draft += text
	case "thought":
		tc.Thought += text
	case "plan":
		tc.Plan = text
	case "status":
		tc.Status = text
	}
}

// Get returns the current turn content.
func (tm *TurnManager) Get(turnID string) *TurnContent {
	tm.mu.RLock()
	defer tm.mu.RUnlock()
	if tc, ok := tm.turns[turnID]; ok {
		return tc
	}
	return &TurnContent{}
}

// Clear removes a completed turn.
func (tm *TurnManager) Clear(turnID string) {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	delete(tm.turns, turnID)
}

// SetPanel sets panel expand/collapse state.
func (tm *TurnManager) SetPanel(turnID, panelID string, expanded bool) {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	if _, ok := tm.panels[turnID]; !ok {
		tm.panels[turnID] = make(map[string]bool)
	}
	tm.panels[turnID][panelID] = expanded
}

// GetPanels returns panel states for a turn.
func (tm *TurnManager) GetPanels(turnID string) map[string]bool {
	tm.mu.RLock()
	defer tm.mu.RUnlock()
	if p, ok := tm.panels[turnID]; ok {
		return p
	}
	return map[string]bool{}
}

// getTurnPreview returns the handler for GET /agent/turn/{id}.
func getTurnPreviewHandler(tm *TurnManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		turnID := chi.URLParam(r, "id")
		tc := tm.Get(turnID)
		jsonResp(w, tc)
	}
}

// setTurnPanelHandler returns the handler for POST /agent/turn/{id}/panel.
func setTurnPanelHandler(tm *TurnManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		turnID := chi.URLParam(r, "id")
		var req struct {
			Panel    string `json:"panel"`
			Expanded bool   `json:"expanded"`
		}
		if err := decodeJSON(r, &req); err != nil || req.Panel == "" {
			jsonError(w, "panel is required", http.StatusBadRequest)
			return
		}
		tm.SetPanel(turnID, req.Panel, req.Expanded)
		jsonResp(w, map[string]string{"status": "ok"})
	}
}
