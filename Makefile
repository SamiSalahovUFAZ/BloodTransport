PYTHON ?= python3
PORT ?= 5002

.PHONY: install run test check up down

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

run:
	$(PYTHON) -m flask --app src.app run --port $(PORT)

test:
	$(PYTHON) -m pytest -q

check:
	$(PYTHON) -m ruff check src tests
	node --check src/static/dispatcher.js
	node --check src/static/role-queue.js
	$(MAKE) test

up:
	docker compose up --build

down:
	docker compose down
