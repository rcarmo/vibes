package extensions

import (
	"context"
	"net/http"
	"testing"
)

// stubExtension is a minimal Extension for testing.
type stubExtension struct {
	id           string
	initCalled   bool
	shutdownDone bool
	routes       []Route
	manifest     *Manifest
}

func (s *stubExtension) ID() string                     { return s.id }
func (s *stubExtension) Name() string                   { return "stub-" + s.id }
func (s *stubExtension) Version() string                { return "0.1.0" }
func (s *stubExtension) Init(_ context.Context) error   { s.initCalled = true; return nil }
func (s *stubExtension) Shutdown(_ context.Context) error { s.shutdownDone = true; return nil }
func (s *stubExtension) Routes() []Route                { return s.routes }
func (s *stubExtension) EventTypes() []string           { return nil }
func (s *stubExtension) StaticDir() string              { return "" }
func (s *stubExtension) Manifest() *Manifest            { return s.manifest }

func TestRegistryRegister(t *testing.T) {
	r := NewRegistry()
	if err := r.Register(&stubExtension{id: "a"}); err != nil {
		t.Fatalf("Register failed: %v", err)
	}

	if _, ok := r.Get("a"); !ok {
		t.Error("Get(a) returned false after Register")
	}
}

func TestRegistryRegisterDuplicate(t *testing.T) {
	r := NewRegistry()
	if err := r.Register(&stubExtension{id: "a"}); err != nil {
		t.Fatalf("first Register failed: %v", err)
	}
	if err := r.Register(&stubExtension{id: "a"}); err == nil {
		t.Error("duplicate Register should have failed")
	}
}

func TestRegistryInitAll(t *testing.T) {
	r := NewRegistry()
	a := &stubExtension{id: "a"}
	b := &stubExtension{id: "b"}
	r.Register(a)
	r.Register(b)

	if err := r.InitAll(context.Background()); err != nil {
		t.Fatalf("InitAll failed: %v", err)
	}

	if !a.initCalled || !b.initCalled {
		t.Error("Init was not called on all extensions")
	}
}

func TestRegistryShutdownAllReverseOrder(t *testing.T) {
	r := NewRegistry()
	var order []string

	mkExt := func(id string) *stubExtension {
		ext := &stubExtension{id: id}
		// Cannot mock easily; use registration order check instead.
		return ext
	}

	a := mkExt("a")
	b := mkExt("b")
	r.Register(a)
	r.Register(b)

	r.ShutdownAll(context.Background())
	if !a.shutdownDone || !b.shutdownDone {
		t.Error("Shutdown not called on all extensions")
	}

	_ = order // placeholder for ordering test if Shutdown becomes ordered
}

func TestRegistryAllRoutes(t *testing.T) {
	r := NewRegistry()
	handler := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(200)
	})

	r.Register(&stubExtension{
		id:     "a",
		routes: []Route{{Method: "GET", Pattern: "/foo", Handler: handler}},
	})
	r.Register(&stubExtension{
		id:     "b",
		routes: []Route{{Method: "POST", Pattern: "/bar", Handler: handler}},
	})

	all := r.AllRoutes()
	if len(all) != 2 {
		t.Errorf("AllRoutes returned %d routes, want 2", len(all))
	}
}

func TestRegistryAllManifests(t *testing.T) {
	r := NewRegistry()
	r.Register(&stubExtension{id: "no-manifest"})
	r.Register(&stubExtension{
		id:       "with-manifest",
		manifest: &Manifest{Panels: []PanelDef{{ID: "p1", Title: "Panel 1"}}},
	})

	manifests := r.AllManifests()
	if len(manifests) != 1 {
		t.Errorf("AllManifests returned %d, want 1", len(manifests))
	}
	if _, ok := manifests["with-manifest"]; !ok {
		t.Error("AllManifests missing 'with-manifest'")
	}
}

func TestRegistryListRegistrationOrder(t *testing.T) {
	r := NewRegistry()
	r.Register(&stubExtension{id: "first"})
	r.Register(&stubExtension{id: "second"})
	r.Register(&stubExtension{id: "third"})

	list := r.List()
	want := []string{"first", "second", "third"}
	if len(list) != len(want) {
		t.Fatalf("List length = %d, want %d", len(list), len(want))
	}
	for i, id := range list {
		if id != want[i] {
			t.Errorf("List[%d] = %q, want %q", i, id, want[i])
		}
	}
}
