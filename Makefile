.PHONY: help install install-dev lint format test coverage check clean bump-patch push serve lint-frontend

PYTHON ?= python3
PIP ?= pip3

# Server configuration
export VIBES_HOST ?= 0.0.0.0
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

lint-frontend: ## Run frontend lint with bun
	bun run lint:frontend

format: ## Format code with ruff
	ruff format src tests

test: ## Run pytest
	$(PYTHON) -m pytest

coverage: ## Run pytest with coverage
	$(PYTHON) -m pytest --cov=src/vibes --cov-report=term-missing

check: lint test ## Run lint + tests

serve: ## Run the web server
	VIBES_HOST=$(VIBES_HOST) VIBES_PORT=$(VIBES_PORT) $(PYTHON) -m vibes.app

# =============================================================================
# Clean targets
# =============================================================================

clean: ## Remove Python cache files
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache __pycache__ src/**/__pycache__ src/*.egg-info

# =============================================================================
# Version management
# =============================================================================

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
