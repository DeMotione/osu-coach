# Development shortcuts (Linux / macOS). Every target is a plain command you can also run by hand.
PY ?= python3

.PHONY: help install api web build test lint openapi e2e app

help:                ## list the targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:             ## Python packages (editable, with dev tools) and the web app's dependencies
	$(PY) -m pip install -c constraints.txt -e "./backend[dev]"
	cd frontend && npm ci

api:                 ## the API on :8501 (reloads nothing: restart after Python changes)
	osu-coach-api

web:                 ## the web app dev server on :5173 (needs `make api` running)
	cd frontend && npm run dev

build:               ## build the web app (served by the API at /)
	cd frontend && npm run build

openapi:             ## regenerate the web app's API types after a schema change
	$(PY) -m osu_coach.app.openapi frontend/src/api/openapi.json
	cd frontend && npm run gen:api

lint:                ## ruff (lint + format check), import layering, TypeScript, ESLint
	cd backend && ruff check . && ruff format --check . && lint-imports
	cd frontend && npm run typecheck && npm run lint

test:                ## Python and web unit tests
	cd backend && $(PY) -m pytest
	cd frontend && npm test

e2e: build           ## end-to-end tests: the built app on the real API
	cd frontend && OSU_COACH_PYTHON=$(PY) npm run e2e

app: build           ## open the app
	osu-coach ui
