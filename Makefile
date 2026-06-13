.DEFAULT_GOAL := help
DC := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Local (uv) -------------------------------------------------------------

.PHONY: install
install: ## Install dependencies with uv
	uv sync

.PHONY: migrate
migrate: ## Apply database migrations
	uv run python manage.py migrate

.PHONY: run
run: ## Run the dev server
	uv run python manage.py runserver

.PHONY: seed
seed: ## Seed demo data
	uv run python manage.py seed_demo

.PHONY: test
test: ## Run the test suite
	uv run pytest

.PHONY: lint
lint: ## Lint and format-check
	uv run ruff check .
	uv run ruff format --check .

.PHONY: fmt
fmt: ## Auto-format
	uv run ruff check --fix .
	uv run ruff format .

.PHONY: worker
worker: ## Run a Celery worker locally
	uv run celery -A config worker -l info

.PHONY: beat
beat: ## Run Celery beat locally
	uv run celery -A config beat -l info

# --- Docker -----------------------------------------------------------------

.PHONY: up
up: ## Build and start the full stack
	$(DC) up --build

.PHONY: down
down: ## Stop the stack
	$(DC) down

.PHONY: logs
logs: ## Tail all service logs
	$(DC) logs -f
