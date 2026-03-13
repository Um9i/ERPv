PYTHON = .venv/bin/python
PYTEST = .venv/bin/pytest

.PHONY: dev prod test test-coverage lint format check mypy audit migrate shell clean lint-migrations seed build

dev:
	podman compose up --build

prod:
	podman compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

test:
	DEBUG=True SECRETKEY=test-secret $(PYTEST) -o "addopts=" --tb=short -q -n auto

test-coverage:
	DEBUG=True SECRETKEY=test-secret $(PYTEST) -o "addopts=" --tb=short -n auto --cov=. --cov-report=html --cov-report=term-missing

seed:
	DEBUG=True SECRETKEY=test-secret $(PYTHON) manage.py seeddata

build:
	podman build -t erpv .

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check --fix .

check:
	$(PYTHON) -m black --check .
	$(PYTHON) -m ruff check .

MYPY_TARGETS = finance/ \
	config/models.py dashboards/models.py \
	inventory/models.py inventory/services.py \
	sales/models.py sales/services.py \
	procurement/models.py procurement/services.py \
	production/models.py production/services.py

mypy:
	$(PYTHON) -m mypy $(MYPY_TARGETS)

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
