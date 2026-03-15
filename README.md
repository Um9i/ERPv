<div align="center">

<p align="center">
  <img src="docs/social-preview.png" alt="Social Preview" width="100%">
</p>

**A modern, open-source ERP built with Django — covering everything from purchase orders to production, shipping to finance.**

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)
[![Django 6.0](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)
[![Tests](https://img.shields.io/badge/tests-650%2B%20passing-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-86%25-brightgreen.svg)](#testing)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[**Live Demo →**](https://um9i.dev/)

</div>

---

ERPv is a full-featured ERP web application designed for small-to-medium manufacturing and distribution businesses. It connects your inventory, procurement, production, sales, and finance workflows in a single system — with multi-site pairing, PDF invoices, and real-time dashboards out of the box.

## Screenshots

<p align="center">
  <img src="docs/screenshots/production.png" alt="Production Management" width="100%">
</p>
<p align="center"><em>Production Management — BOM tracking, manufacturing jobs, and shortage analysis</em></p>

<p align="center">
  <img src="docs/screenshots/inventory.png" alt="Inventory Management" width="100%">
</p>
<p align="center"><em>Inventory Management — stock health, shortfall alerts, and warehouse overview</em></p>

<p align="center">
  <img src="docs/screenshots/finance.png" alt="Finance Overview" width="100%">
</p>
<p align="center"><em>Finance Overview — sales & purchase ledgers, profit tracking, and stock valuation</em></p>

## What's Inside

🏭 **Inventory** — Product catalogue with images, hierarchical warehouse locations (Warehouse → Zone → Bin), stock transfers, demand analysis, health dashboards, and a full audit ledger.

🛒 **Procurement** — Manage suppliers and contacts, raise purchase orders, track receiving workflows with scan-to-receive barcode matching, reusable PO templates, and monitor supplier product costs through the purchase ledger.

⚙️ **Production** — Recursive Bill of Materials with an interactive tree visualiser, manufacturing jobs with due-date tracking, component shortage analysis, cost roll-ups, and margin analysis.

📦 **Sales** — Customer management, sales orders with pick lists, scan-to-pick confirmation with barcode/QR scanning, bulk close actions on list pages, shipment processing with real-time stock checks, and PDF invoice generation via WeasyPrint.

💰 **Finance** — Sales and purchase ledgers with filtering and CSV export, monthly breakdowns, outstanding orders reports, product-level P&L, and a 12-month sales vs purchases chart.

📊 **Dashboards** — Shipping and delivery schedules with day/week navigation, overdue order tracking, and per-module dashboards with search and KPI cards.

🔗 **Multi-site Pairing** — Connect multiple ERPv instances together with API-key authentication, browse remote catalogues, and automatically import suppliers and customers across sites. Purchase orders created against a paired supplier are automatically forwarded to the remote instance, which auto-creates a matching sales order and notifies the supplier.

🔔 **Notifications** — In-app notification centre with a navbar bell badge, low stock alerts, overdue order warnings, and order status change notifications. Optional email delivery of alert digests. Run `check_notifications` periodically for proactive alerts.

🔒 **Security & Reliability** — Rate limiting on all API endpoints and login, granular role-based permissions with 12 custom permissions across all modules, soft deletes for critical models (Product, Supplier, PurchaseOrder, Customer, SalesOrder, Production), Sentry integration for production error tracking, and webhook delivery retry with exponential backoff.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 6.0.3, Python 3.14 |
| Database | PostgreSQL (production), SQLite (development) |
| Frontend | Bootstrap 5 via django-crispy-forms, TypeScript |
| PDF Generation | WeasyPrint |
| QR Codes | python-qrcode |
| Static Files | WhiteNoise |
| Server | Gunicorn |
| Testing | pytest, pytest-xdist, factory_boy — 650+ tests, 86% coverage |
| Code Quality | ruff, mypy, bandit, pip-audit, pre-commit |

## Quick Start

### Option 1: Docker (recommended)

The fastest way to get up and running. Docker Compose spins up PostgreSQL and the app together:

```bash
docker compose up --build
```

The entrypoint script handles migrations, static file collection, and starts Gunicorn on port **8000** — you just need to set a few environment variables:

| Variable | Default | Description |
|---|---|---|
| `SECRETKEY` | *(required in production)* | Django secret key |
| `DEBUG` | `False` | Set `True` for development |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames |
| `DATABASE_URL` | SQLite fallback | PostgreSQL connection URL |
| `CURRENCY_SYMBOL` | `£` | Currency symbol shown in the UI |

### Option 2: Local Development

```bash
# 1. Clone and set up a virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes production deps + dev tooling

# 2. Configure your environment
export DEBUG=True
export SECRETKEY="your-secret-key"       # optional when DEBUG=True
export ALLOWED_HOSTS="localhost,127.0.0.1"

# 3. Run migrations and start the server
python manage.py migrate
python manage.py runserver
```

To use PostgreSQL locally, set `DATABASE_URL`:

```bash
export DATABASE_URL="postgres://user:password@localhost:5432/erpv"
```

Without it, the app falls back to a local SQLite file — fine for development.

> **Production note:** When `DEBUG=False`, `SECRETKEY` is mandatory and security headers (HSTS, SSL redirect, secure cookies) are enabled automatically.

## Testing

Tests run with pytest and include coverage reporting:

```bash
pytest                        # run all 650+ tests
pytest -m unit                # unit tests only
pytest -m integration         # integration tests only
pytest -m e2e                 # end-to-end workflow tests
pytest -m "integration and not e2e"  # integration without e2e
```

Coverage reports are generated in `htmlcov/`. CI enforces an **85% coverage threshold** — the current suite achieves ~87%.

### Code Quality

The project uses [pre-commit](https://pre-commit.com/) hooks to keep things clean:

```bash
pre-commit install          # one-time setup
pre-commit run --all-files  # manual run
```

This runs **ruff** (formatting & linting) and **bandit** (security scanning) automatically.

Type checking via mypy:

```bash
mypy .                      # check entire project
mypy finance/               # check a single module
```

## CI/CD

GitHub Actions runs on every push and pull request to `master`:

| Job | What it does |
|---|---|
| **lint** | ruff format + lint, TypeScript type check, migration lint |
| **security** | bandit scan + pip-audit dependency check |
| **typecheck** | mypy across models, services, and finance |
| **test** | Unit tests then integration tests (pytest) |
| **build** | Docker image build (runs after all checks pass) |

## Project Structure

```
main/          # Settings, URLs, middleware, template tags, and test factories
inventory/     # Stock management, warehouse locations, ledger, and catalogue API
procurement/   # Suppliers, purchase orders, receiving, and notifications
production/    # BOM management, manufacturing jobs, cost roll-up, and visualiser
sales/         # Customers, sales orders, shipping, and PDF invoices
finance/       # Ledger views, CSV export, outstanding orders, and product P&L
config/        # Company configuration and paired instance management
dashboards/    # Shipping and delivery schedule views
tests/         # Unit, integration, and end-to-end tests (pytest)
docs/          # Module-level documentation
templates/     # HTML templates
static/        # Static assets and TypeScript source
```

## Documentation

Each module has its own detailed docs in the [`docs/`](docs/) directory:

- [Inventory](docs/inventory.md) — stock tracking, locations, adjustments, and the catalogue API
- [Procurement](docs/procurement.md) — suppliers, purchase orders, and receiving
- [Production](docs/production.md) — BOMs, manufacturing jobs, and cost analysis
- [Sales](docs/sales.md) — customers, orders, shipping, and invoicing
- [Finance](docs/finance.md) — ledgers, P&L, and the finance dashboard

## License

MIT — see [LICENSE](LICENSE) for details.
