# Contributing to ERPv

Thanks for your interest in contributing! This guide will help you get set up and submit a quality pull request.

## Getting Started

1. **Fork** the repository and clone your fork.
2. Create a virtual environment and install dev dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

3. Set up pre-commit hooks:

   ```bash
   pre-commit install
   ```

4. Run migrations and start the dev server:

   ```bash
   export DEBUG=True
   python manage.py migrate
   python manage.py runserver
   ```

   Or use Docker:

   ```bash
   docker compose up --build
   ```

## Making Changes

1. Create a feature branch from `master`:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes. Keep commits focused — one logical change per commit.
3. Add or update tests for any new or changed behaviour.
4. Run the full check suite before pushing:

   ```bash
   make check        # ruff format + lint + TypeScript type check
   make test         # run all tests
   make mypy         # type checking
   ```

## Code Style

- **Python** — Formatted and linted with [ruff](https://github.com/astral-sh/ruff). Pre-commit hooks handle this automatically.
- **TypeScript** — Type-checked with `tsc` (run via `make tsc` or `make check`).
- **Line length** — No hard limit enforced (`E501` is ignored), but keep lines reasonable.
- **Imports** — Sorted by ruff (isort rules enabled).

## Testing

Tests use **pytest** with **factory_boy** for fixtures. The project has 500+ tests across three categories:

```bash
pytest -m unit           # fast, isolated unit tests
pytest -m integration    # view-level and cross-module tests
pytest -m e2e            # full end-to-end workflow tests
```

When adding tests:
- Place them in the `tests/` directory, mirroring the module structure.
- Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, or `@pytest.mark.e2e`.
- Use existing factories from `main/factories.py` where possible.

## Pull Requests

- Target the `master` branch.
- Give your PR a clear title and description of **what** changed and **why**.
- Ensure CI passes — the pipeline runs linting, security checks, type checking, and tests.
- Keep PRs small and focused. Large changes are harder to review.

## Reporting Bugs

Open an issue with:
- Steps to reproduce the problem.
- Expected vs actual behaviour.
- Browser/OS details if it's a UI issue.

## Project Structure

Each module is self-contained with its own models, views, admin, and URLs:

```
inventory/     Stock management, warehouse locations, catalogue API
procurement/   Suppliers, purchase orders, receiving
production/    BOMs, manufacturing jobs, cost analysis
sales/         Customers, orders, shipping, invoicing
finance/       Ledgers, P&L, finance dashboard
config/        Company configuration, paired instances
dashboards/    Shipping and delivery schedules
```

Module-level docs are in [`docs/`](docs/).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
