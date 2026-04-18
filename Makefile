.PHONY: all build clean test test-acp serve dev frontend lint

BINARY = vibes
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS = -ldflags "-s -w -X main.version=$(VERSION)"

all: build

build:
	go build $(LDFLAGS) -o $(BINARY) ./cmd/vibes/

clean:
	rm -f $(BINARY)
	go clean

test:
	go test ./...

test-acp:
	go run cmd/acp-test/main.go

serve: build
	VIBES_DEBUG=true ./$(BINARY)

dev:
	VIBES_DEBUG=true go run ./cmd/vibes/

frontend:
	bun run build.js

lint:
	go vet ./...

# Cross-compile targets
build-linux-amd64:
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o $(BINARY)-linux-amd64 ./cmd/vibes/

build-linux-arm64:
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY)-linux-arm64 ./cmd/vibes/

build-darwin-arm64:
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY)-darwin-arm64 ./cmd/vibes/

build-all: build-linux-amd64 build-linux-arm64 build-darwin-arm64

check: lint test test-acp
