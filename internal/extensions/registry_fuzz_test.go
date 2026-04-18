package extensions

import (
	"context"
	"testing"
)

// FuzzRegistryRegisterID ensures Register handles arbitrary extension IDs
// without panicking and rejects duplicates correctly.
func FuzzRegistryRegisterID(f *testing.F) {
	f.Add("normal-id")
	f.Add("")
	f.Add("with spaces")
	f.Add("with/slash")
	f.Add("with-null")
	f.Add("very-long-id-" + string(make([]byte, 1000)))

	f.Fuzz(func(t *testing.T, id string) {
		r := NewRegistry()
		ext := &stubExtension{id: id}

		// First register should succeed.
		err1 := r.Register(ext)
		// Second register with same ID should fail.
		err2 := r.Register(&stubExtension{id: id})

		if err1 == nil && err2 == nil {
			t.Errorf("duplicate registration not rejected for id=%q", id)
		}

		// InitAll should never panic regardless of ID content.
		_ = r.InitAll(context.Background())
		r.ShutdownAll(context.Background())
	})
}
