.PHONY: help install install-dev lint format test test-parity fixtures-vibes coverage check check-all clean bump-minor bump-patch push serve lint-frontend build-frontend test-frontend

PYTHON ?= python3
PIP ?= pip3

# Rebuildable caches and scratch only; retained evidence stays in docs/evidence.
# Resolve once using the original environment, before exporting child TMPDIR.
VIBES_TMP_ROOT := $(shell PROJECT=vibes bash scripts/project-tmp.sh init | sed -n 's/^PROJECT_TMP_ROOT=//p')
ifeq ($(strip $(VIBES_TMP_ROOT)),)
$(error Cannot resolve safe project scratch root; check PROJECT_TMP_ROOT)
endif
export PROJECT_TMP_ROOT := $(VIBES_TMP_ROOT)
VIBES_RUN_ID ?= $(shell date -u +%Y%m%dT%H%M%S)-$(shell echo $$$$)
VIBES_RUN_DIR := $(VIBES_TMP_ROOT)/runs/make/$(VIBES_RUN_ID)
export TMPDIR := $(VIBES_RUN_DIR)/tmp
export TMP := $(TMPDIR)
export TEMP := $(TMPDIR)
export XDG_CACHE_HOME := $(VIBES_TMP_ROOT)/cache/xdg
export PIP_CACHE_DIR := $(VIBES_TMP_ROOT)/cache/pip
export UV_CACHE_DIR := $(VIBES_TMP_ROOT)/cache/uv
export BUN_INSTALL_CACHE_DIR := $(VIBES_TMP_ROOT)/cache/bun
export npm_config_cache := $(VIBES_TMP_ROOT)/cache/npm
export PYTHONPYCACHEPREFIX := $(VIBES_TMP_ROOT)/cache/python
export PYTEST_ADDOPTS := --basetemp=$(VIBES_RUN_DIR)/pytest -o cache_dir=$(VIBES_TMP_ROOT)/cache/pytest $(PYTEST_ADDOPTS)
export VIBES_BUILD_DIR := $(VIBES_TMP_ROOT)/build
# Create roots without depending on a recipe's current directory.
_tmp_init := $(shell mkdir -p $(TMPDIR) $(XDG_CACHE_HOME) $(PIP_CACHE_DIR) $(UV_CACHE_DIR) $(BUN_INSTALL_CACHE_DIR) $(npm_config_cache) $(PYTHONPYCACHEPREFIX) $(VIBES_BUILD_DIR))

# Server configuration
export VIBES_HOST ?= 127.0.0.1
export VIBES_PORT ?= 8080
export VIBES_ACP_AGENT ?= copilot --acp

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# Python targets
# =============================================================================

install: ## Install package in editable mode
	$(PIP) install -e .

install-dev: install ## Install with dev dependencies
	$(PIP) install -e ".[dev]"
	$(PIP) install ruff

lint: ## Run ruff linter
	ruff check src tests

# Web front-end: owned in rcarmo/fixtures-vibes (ui/vibes); src/vibes/static links into this submodule.
VIBES_UI := references/fixtures-vibes/ui/vibes

lint-frontend: ## Run frontend lint with bun
	$(MAKE) -C $(VIBES_UI) lint PROJECT_NAME=vibes PROJECT_TMP_ROOT=$(VIBES_TMP_ROOT)

build-frontend: ## Bundle frontend JS with bun
	$(MAKE) -C $(VIBES_UI) build PROJECT_NAME=vibes PROJECT_TMP_ROOT=$(VIBES_TMP_ROOT)

test-frontend: ## Front-end unit tests and browser harnesses (fixtures-vibes ui/vibes)
	$(MAKE) -C $(VIBES_UI) test browser PROJECT_NAME=vibes PROJECT_TMP_ROOT=$(VIBES_TMP_ROOT)
	bun test ./tests/frontend/

format: ## Format code with ruff
	ruff format src tests

test: ## Run pytest
	PYTHONPATH=src $(PYTHON) -m pytest

test-parity: ## Compatibility alias for shared fixtures-vibes compliance
	bun run test:parity

fixtures-vibes: ## Run the shared Classic compliance suite
	$(MAKE) -C references/fixtures-vibes deps compliance PROJECT_NAME=vibes PROJECT_TMP_ROOT=$(VIBES_TMP_ROOT) PROFILE=$(CURDIR)/tests/fixtures-vibes/profile.json

coverage: ## Run pytest with coverage
	PYTHONPATH=src $(PYTHON) -m pytest --cov=src/vibes --cov-report=term-missing

check: lint test ## Run lint + tests

check-all: lint lint-frontend coverage ## Run all lints + tests with coverage

serve: ## Run the web server
	PYTHONPATH=src VIBES_HOST=$(VIBES_HOST) VIBES_PORT=$(VIBES_PORT) $(PYTHON) -m vibes.app

# =============================================================================
# Clean targets
# =============================================================================

clean: ## Remove Python cache files
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache __pycache__ src/**/__pycache__ src/*.egg-info

# =============================================================================
# Version management
# =============================================================================

bump-minor: ## Bump minor version, reset patch, and create git tag
	@OLD=$$(grep -Po '(?<=^version = ")[^"]+' pyproject.toml); \
	MAJOR=$$(echo $$OLD | cut -d. -f1); \
	MINOR=$$(echo $$OLD | cut -d. -f2); \
	NEW="$$MAJOR.$$((MINOR + 1)).0"; \
	sed -i "s/^version = \"$$OLD\"/version = \"$$NEW\"/" pyproject.toml; \
	git add pyproject.toml; \
	git commit -m "Bump version to $$NEW"; \
	git tag "v$$NEW"; \
	echo "Bumped version: $$OLD -> $$NEW (tagged v$$NEW)"

bump-patch: ## Bump patch version and create git tag
	@OLD=$$(grep -Po '(?<=^version = ")[^"]+' pyproject.toml); \
	MAJOR=$$(echo $$OLD | cut -d. -f1); \
	MINOR=$$(echo $$OLD | cut -d. -f2); \
	PATCH=$$(echo $$OLD | cut -d. -f3); \
	NEW="$$MAJOR.$$MINOR.$$((PATCH + 1))"; \
	sed -i "s/^version = \"$$OLD\"/version = \"$$NEW\"/" pyproject.toml; \
	git add pyproject.toml; \
	git commit -m "Bump version to $$NEW"; \
	git tag "v$$NEW"; \
	echo "Bumped version: $$OLD -> $$NEW (tagged v$$NEW)"

push: ## Push commits and current tag to origin
	@TAG=$$(git describe --tags --exact-match 2>/dev/null); \
	git push origin main; \
	if [ -n "$$TAG" ]; then \
		echo "Pushing tag $$TAG..."; \
		git push origin "$$TAG"; \
	else \
		echo "No tag on current commit"; \
	fi

.PHONY: test-browser
# WebKit popup automation requires a display on Linux; use Xvfb in CI.
test-browser: build-frontend
	xvfb-run -a -s "-screen 0 1920x1080x24" bun x playwright test --headed --workers=1 --trace retain-on-failure
