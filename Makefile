# Shortcuts for local development. Run `make` to list them.
# Works with the make shipped with macOS (GNU make 3.81).

SERVER := server
DESKTOP := desktop
HOST ?= 127.0.0.1
PORT ?= 8000

# Desktop app options, e.g. `make desktop-start PROFILE=ana SERVER_URL=http://10.0.0.5:8000`.
#   SERVER_URL  server the app talks to (default: the one saved on the login screen, else localhost:8000)
#   PROFILE     separate login and settings, to run several users side by side (kept in desktop/.profiles/)
SERVER_URL ?=
PROFILE ?=
DESKTOP_ENV := $(if $(SERVER_URL),AIB_SERVER_URL=$(SERVER_URL)) \
	$(if $(PROFILE),AIB_USER_DATA=$(abspath $(DESKTOP))/.profiles/$(PROFILE))

.DEFAULT_GOAL := help
.PHONY: help install migrate seed reset-demo server desktop dev \
	desktop-build desktop-start desktop-dist desktop-dist-mac desktop-dist-win desktop-dist-linux desktop-clean \
	test test-server test-desktop typecheck e2e \
	docker-demo docker-up docker-down secret

help: ## List the available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Local development -------------------------------------------------------

install: ## Install server and desktop dependencies
	cd $(SERVER) && uv sync
	cd $(DESKTOP) && npm install

migrate: ## Apply database migrations
	cd $(SERVER) && uv run python manage.py migrate

seed: migrate ## Create the demo users and classes (keeps existing ones)
	cd $(SERVER) && uv run python manage.py seed_demo

reset-demo: migrate ## Rebuild the demo users and classes from scratch
	cd $(SERVER) && uv run python manage.py seed_demo --reset

server: migrate ## Start the server (HOST and PORT default to 127.0.0.1 and 8000)
	cd $(SERVER) && uv run daphne -b $(HOST) -p $(PORT) config.asgi:application

desktop: ## Start the desktop app in development mode, with hot reload
	cd $(DESKTOP) && $(DESKTOP_ENV) npm run dev

dev: migrate ## Start the server and the desktop app together (Ctrl-C stops both)
	$(MAKE) -j2 server desktop

# --- Desktop app: build and package ---------------------------------------------

desktop-build: ## Build the desktop app into desktop/out/
	cd $(DESKTOP) && npm run build

desktop-start: desktop-build ## Build and run the desktop app as in production (no dev server)
	cd $(DESKTOP) && $(DESKTOP_ENV) npx electron .

desktop-dist: desktop-build ## Package an installer for this OS into desktop/dist/
	cd $(DESKTOP) && npx electron-builder

desktop-dist-mac: desktop-build ## Package the macOS .dmg
	cd $(DESKTOP) && npx electron-builder --mac

desktop-dist-win: desktop-build ## Package the Windows installer (.exe)
	cd $(DESKTOP) && npx electron-builder --win

desktop-dist-linux: desktop-build ## Package the Linux .AppImage
	cd $(DESKTOP) && npx electron-builder --linux

desktop-clean: ## Remove desktop build output, installers and local profiles
	rm -rf $(DESKTOP)/out $(DESKTOP)/dist $(DESKTOP)/.profiles

# --- Checks ------------------------------------------------------------------

test: test-server test-desktop ## Run all unit tests

test-server: ## Run the server tests (set DATABASE_URL to use Postgres)
	cd $(SERVER) && uv run pytest

test-desktop: ## Run the desktop unit tests
	cd $(DESKTOP) && npm test

typecheck: ## Type-check the desktop app
	cd $(DESKTOP) && npm run typecheck

e2e: ## Run the Electron smoke test (needs `make reset-demo` and `make server` running)
	cd $(DESKTOP) && npm run e2e

# --- Docker ------------------------------------------------------------------

docker-demo: ## Offline demo in Docker: seeded data, fake LLM, dev secret key
	DJANGO_DEBUG=1 SEED_DEMO=1 LLM_PROVIDER=fake docker compose up --build

docker-up: ## Production-like stack in Docker (needs DJANGO_SECRET_KEY in .env)
	docker compose up --build

docker-down: ## Stop the Docker stack
	docker compose down

secret: ## Print a new value for DJANGO_SECRET_KEY
	@python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
