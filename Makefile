.PHONY: help install lint format test test-acp serve dev frontend frontend-fast bundle clean check build build-go build-all build-linux-amd64 build-linux-arm64 build-darwin-arm64 push

BINARY = vibes
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS = -ldflags "-s -w -X main.version=$(VERSION)"
STATIC_DIR = static

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Download Go dependencies
	go mod download

node_modules: package.json
	bun install
	@touch node_modules

frontend: node_modules ## Build frontend bundle (typecheck + build)
	bun run build.js

frontend-fast: node_modules ## Build frontend without typecheck (dev iteration)
	bun run build.js

bundle: frontend ## Alias for frontend

build-go: ## Build Go binary (assumes frontend is already built)
	@if [ ! -d "$(STATIC_DIR)/dist" ]; then \
		echo "ERROR: $(STATIC_DIR)/dist not found. Run 'make frontend' first."; \
		exit 1; \
	fi
	go build $(LDFLAGS) -o $(BINARY) ./cmd/vibes/
	@echo "Built $(BINARY) ($(shell du -h $(BINARY) | cut -f1))"

build: frontend build-go ## Full build: frontend + Go binary

# Cross-compile targets
build-linux-amd64: frontend ## Build for Linux x86_64
	GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o $(BINARY)-linux-amd64 ./cmd/vibes/

build-linux-arm64: frontend ## Build for Linux ARM64 (Raspberry Pi, ARM Proxmox)
	GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY)-linux-arm64 ./cmd/vibes/

build-darwin-arm64: frontend ## Build for macOS Apple Silicon
	GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY)-darwin-arm64 ./cmd/vibes/

build-all: build-linux-amd64 build-linux-arm64 build-darwin-arm64 ## Build for all supported platforms

lint: ## Run go vet
	go vet ./...

format: ## Format Go code
	gofmt -w ./cmd ./internal ./embed.go

test: ## Run Go tests
	go test ./...

test-acp: ## Run ACP integration test (spawns copilot/codex/claude agents)
	go run cmd/acp-test/main.go

check: lint test ## Run lint + tests

serve: build ## Build and run with debug logging
	VIBES_DEBUG=true ./$(BINARY)

dev: ## Run from source with debug logging (skips frontend build)
	VIBES_DEBUG=true go run ./cmd/vibes/

clean: ## Remove build artifacts
	rm -f $(BINARY) $(BINARY)-*
	go clean

clean-all: clean ## Remove build artifacts and frontend dependencies
	rm -rf node_modules bun.lock $(STATIC_DIR)/dist

push: ## Push current branch and any tags pointing at HEAD
	@BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	git push origin $$BRANCH && git push origin --tags
