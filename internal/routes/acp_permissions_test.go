package routes

import (
	"testing"

	"github.com/rcarmo/vibes/internal/agent/acp"
)

func TestACPOptionsToRouteOptions(t *testing.T) {
	options := acpOptionsToRouteOptions([]acp.PermissionOption{
		{ID: "allow", Name: "Allow once", Kind: "allow_once"},
		{ID: "deny"},
	})
	if len(options) != 2 {
		t.Fatalf("len = %d", len(options))
	}
	if options[0].ID != "allow" || options[0].Label != "Allow once (allow_once)" {
		t.Fatalf("first option = %#v", options[0])
	}
	if options[1].ID != "deny" || options[1].Label != "deny" {
		t.Fatalf("second option = %#v", options[1])
	}
}
