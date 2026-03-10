PYTHON = .venv/bin/python
PYTEST = .venv/bin/pytest

.PHONY: dev prod test lint format check mypy audit migrate shell clean lint-migrations

dev:
	podman compose up --build

prod:
	podman compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

test:
	DEBUG=True SECRETKEY=test-secret $(PYTEST) -o "addopts=" --tb=short -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check --fix .

check:
	$(PYTHON) -m black --check .
	$(PYTHON) -m ruff check .

mypy:
	$(PYTHON) -m mypy finance/

audit:
	$(PYTHON) -m bandit -r . --exclude ./.venv,./tests -q
	$(PYTHON) -m pip_audit

migrate:
	$(PYTHON) manage.py migrate

lint-migrations:
	DEBUG=True SECRETKEY=test-secret $(PYTHON) manage.py lintmigrations --no-cache

shell:
	$(PYTHON) manage.py shell

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf htmlcov .coverage .mypy_cache .ruff_cache .pytest_cache
