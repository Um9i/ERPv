# ERPv

A Django-based ERP (Enterprise Resource Planning) web application covering inventory, procurement, production, sales, and finance management.

## Features

| Module | Description |
|---|---|
| **Inventory** | Product catalogue with images, stock tracking, hierarchical warehouse locations (Warehouse → Zone → Bin), stock transfers, catalogue API, full audit ledger, stock health dashboard, and demand analysis |
| **Procurement** | Suppliers, supplier contacts, purchase orders with receiving workflows, purchase ledger, and supplier product cost tracking |
| **Production** | Recursive Bill of Materials management, interactive BOM visualiser, manufacturing jobs with due-date tracking, component shortage analysis, cost roll-up, margin analysis, and bin-level receiving |
| **Sales** | Customers, customer contacts, sales orders, pick lists, shipment processing with stock availability checks, sales ledger, and PDF invoice generation via WeasyPrint |
| **Finance** | Sales and purchase ledgers with filtering and CSV export, monthly breakdowns, outstanding orders report, product P&L with margin analysis, and a dashboard with 12-month sales vs purchases chart |
| **Dashboards** | Shipping and delivery schedule views with day/week navigation, overdue order tracking, and per-module dashboards with search and KPI metrics |
| **Config** | Company configuration, paired instance management for multi-site ERPv deployments with API-key authentication, remote catalogue browsing, and automated supplier/customer import |

## Tech Stack

- **Backend:** Django 6.0.3, Python 3.14
- **Database:** PostgreSQL (production) / SQLite (development)
- **Frontend:** Bootstrap 5 via django-crispy-forms
- **PDF generation:** WeasyPrint
- **Static files:** WhiteNoise
- **Server:** Gunicorn
- **Testing:** pytest, factory_boy, 227+ tests
- **Quality:** ruff, black, mypy, bandit, pip-audit, pre-commit

## Getting Started

### Local Development

1. **Clone the repository and create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**

   ```bash
   export SECRETKEY="your-secret-key"   # required in production; optional in dev
   export DEBUG=True                     # defaults to False — must opt in for dev
   export ALLOWED_HOSTS="localhost,127.0.0.1"  # comma-separated, defaults shown
   export CURRENCY_SYMBOL="£"
   ```

   For PostgreSQL, set:

   ```bash
   export DATABASE_URL="postgres://user:password@localhost:5432/erpv"
   ```

   Without `DATABASE_URL` the app falls back to the local `db.sqlite3` file.

   > **Note:** When `DEBUG=False`, `SECRETKEY` is mandatory — the app will
   > refuse to start without it. Production security headers (`HSTS`,
   > `SECURE_SSL_REDIRECT`, secure cookies) are enabled automatically.

3. **Run migrations and start the development server:**

   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

### Docker (Recommended for Production)

The repository includes a `docker-compose.yml` that spins up a PostgreSQL database and the Django app together.

```bash
docker compose up --build
```

The entrypoint script waits for the database, runs migrations, collects static files, then starts Gunicorn on port **8000**.

**Key environment variables for Docker:**

| Variable | Default | Description |
|---|---|---|
| `SECRETKEY` | *(required)* | Django secret key – must be set in production |
| `DEBUG` | `False` | Set to `True` for development |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames |
| `DATABASE_URL` | SQLite | Full database connection URL |
| `CURRENCY_SYMBOL` | `£` | Currency symbol used in the UI |

## Running Tests

Tests use pytest with pytest-django and coverage reporting:

```bash
DEBUG=True SECRETKEY=test pytest
```

Coverage reports are written to `htmlcov/`.

### Code Quality

The project uses [pre-commit](https://pre-commit.com/) hooks for automated checks:

```bash
pre-commit install          # one-time setup
pre-commit run --all-files  # manual run
```

Hooks include **black** (formatting), **ruff** (linting), and **bandit** (security).

Type checking is available via mypy (currently scoped to the finance module):

```bash
DEBUG=True SECRETKEY=test mypy finance/
```

## Project Structure

```
main/          # Django project settings, URLs, middleware, template tags, and test factories
inventory/     # Stock management, warehouse locations, ledger, adjustments, and catalogue API
procurement/   # Suppliers, purchase orders, receiving, and supplier product notifications
production/    # BOM management, manufacturing jobs, cost roll-up, and BOM visualiser
sales/         # Customers, sales orders, shipping, and PDF invoices
finance/       # Ledger views, CSV export, outstanding orders, and product P&L reports
config/        # Company configuration and paired instance management
dashboards/    # Shipping and delivery schedule views
docs/          # Module-level documentation
templates/     # HTML templates
static/        # Static assets
```

## Module Documentation

Detailed documentation for each module lives in the [`docs/`](docs/) directory:

- [Inventory](docs/inventory.md)
- [Procurement](docs/procurement.md)
- [Production](docs/production.md)
- [Sales](docs/sales.md)
- [Finance](docs/finance.md)

## License

MIT — see [LICENSE](LICENSE) for details.
