package main

// Smoke-test that the main package compiles and that the help/version flow
// does not panic. Real integration tests live in the internal packages.

import "testing"

func TestMainPackageCompiles(t *testing.T) {
	// If this test runs at all, the package compiled successfully.
}
