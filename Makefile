.PHONY: help install lint lint-frontend typecheck-frontend test-frontend format test race coverage fuzz check serve dev frontend frontend-fast bundle clean clean-all build build-go build-all build-linux-amd64 build-linux-arm64 build-darwin-arm64 push test-acp e2e e2e-setup e2e-teardown

BINARY = vibes
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
LDFLAGS = -ldflags "-s -w -X main.version=$(VERSION)"
STATIC_DIR = static
FUZZTIME ?= 1s
GO_PACKAGES = $(shell go list ./... | grep -v '/node_modules/')

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Download Go dependencies
	go mod download

node_modules: package.json
	bun install
	@touch node_modules

lint-frontend: node_modules ## Run frontend ESLint
	bun run lint:frontend

typecheck-frontend: node_modules ## Type-check converted TypeScript frontend modules
	bun run typecheck:frontend

test-frontend: node_modules ## Run frontend unit tests
	bun run test:frontend

frontend: node_modules typecheck-frontend ## Build frontend bundle (typecheck + build)
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
	@echo "Built $(BINARY) ($(shell du -h $(BINARY) 2>/dev/null | cut -f1))"

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
	go vet $(GO_PACKAGES)

format: ## Format Go code
	gofmt -w ./cmd ./internal ./embed.go

test: ## Run Go tests
	go test $(GO_PACKAGES)

race: ## Run Go tests with race detector
	go test -race $(GO_PACKAGES)

coverage: ## Run tests with coverage report
	go test $(GO_PACKAGES) -coverprofile=coverage.out
	@go tool cover -func=coverage.out | tail -n 1
	@echo "Run 'go tool cover -html=coverage.out' to view detailed coverage"

fuzz: ## Run all fuzz tests briefly (override with FUZZTIME=10s)
	@echo "Running fuzz tests (FUZZTIME=$(FUZZTIME))..."
	@for pkg in $$(go list ./... | xargs -I {} sh -c 'grep -l "^func Fuzz" $$(go list -f "{{.Dir}}" {})/*_test.go 2>/dev/null && echo {}' | grep "^github" | sort -u); do \
		for fuzz in $$(grep -h "^func Fuzz" $$(go list -f "{{.Dir}}" $$pkg)/*_test.go | sed 's/^func \(Fuzz[A-Za-z0-9_]*\).*/\1/'); do \
			echo "  $$pkg :: $$fuzz"; \
			go test $$pkg -run="^$$" -fuzz="^$$fuzz$$" -fuzztime=$(FUZZTIME) || exit 1; \
		done; \
	done

test-acp: ## Run ACP integration test (spawns copilot/codex/claude/pi agents)
	go run cmd/acp-test/main.go

e2e-setup: build ## Start vibes for E2E testing
	@echo "Starting vibes for E2E tests..."
	@VIBES_PORT=8765 VIBES_DEBUG=true \
		./$(BINARY) > /tmp/vibes-e2e.log 2>&1 & echo $$! > /tmp/vibes-e2e.pid
	@sleep 2
	@curl -fsS http://127.0.0.1:8765/health > /dev/null && echo "vibes ready (PID $$(cat /tmp/vibes-e2e.pid))" || \
		(echo "ERROR: vibes failed to start"; cat /tmp/vibes-e2e.log; exit 1)

e2e-teardown: ## Stop the E2E vibes instance
	@if [ -f /tmp/vibes-e2e.pid ]; then \
		kill $$(cat /tmp/vibes-e2e.pid) 2>/dev/null || true; \
		rm -f /tmp/vibes-e2e.pid; \
		echo "vibes stopped"; \
	fi

e2e: e2e-setup ## Run Playwright E2E tests with screenshots + PDF report
	@bunx playwright test; \
	RET=$$?; \
	node scripts/generate-report-pdf.mjs --output test-results/vibes-ux-report.pdf 2>/dev/null || true; \
	$(MAKE) e2e-teardown; \
	echo "Report: test-results/vibes-ux-report.pdf"; \
	echo "Screenshots: test-results/"; \
	exit $$RET

e2e-report: ## Generate PDF report from last test run (no re-run)
	node scripts/generate-report-pdf.mjs --output test-results/vibes-ux-report.pdf

check: lint lint-frontend typecheck-frontend test test-frontend coverage ## Run lint + tests + coverage

serve: build ## Build and run with debug logging
	VIBES_DEBUG=true ./$(BINARY)

dev: ## Run from source with debug logging (skips frontend build)
	VIBES_DEBUG=true go run ./cmd/vibes/

clean: ## Remove build artifacts and coverage
	rm -f $(BINARY) $(BINARY)-* coverage.out
	go clean

clean-all: clean ## Remove build artifacts, coverage, and frontend dependencies
	rm -rf node_modules bun.lock $(STATIC_DIR)/dist

push: ## Push current branch and any tags pointing at HEAD
	@BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	git push origin $$BRANCH && git push origin --tags
