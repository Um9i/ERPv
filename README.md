# ERPv

A Django-based ERP (Enterprise Resource Planning) web application covering inventory, procurement, production, sales, and finance management.

## Features

| Module | Description |
|---|---|
| **Inventory** | Product catalogue, stock tracking, warehouse locations, ledger history, and demand analysis |
| **Procurement** | Suppliers, purchase orders, receiving workflows, and purchase ledger |
| **Production** | Bill of Materials (BOM) management, manufacturing jobs, component allocation, and receiving |
| **Sales** | Customers, sales orders, shipment processing, and sales ledger |
| **Finance** | Dashboard aggregating revenue, purchase costs, and gross profit from ledgers |

## Tech Stack

- **Backend:** Django 6, Python 3.14
- **Database:** PostgreSQL (production) / SQLite (development)
- **Frontend:** Bootstrap 5 via django-crispy-forms
- **PDF generation:** WeasyPrint
- **Static files:** WhiteNoise
- **Server:** Gunicorn

## Getting Started

### Local Development

1. **Clone the repository and create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables** (optional – defaults shown):

   ```bash
   export SECRETKEY="your-secret-key"
   export DEBUG=True
   export CURRENCY_SYMBOL="£"
   ```

   For PostgreSQL, set:

   ```bash
   export DATABASE_URL="postgres://user:password@localhost:5432/erpv"
   ```

   Without `DATABASE_URL` the app falls back to the local `db.sqlite3` file.

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
| `SECRETKEY` | `SECRET` | Django secret key – change in production |
| `DEBUG` | `True` | Set to `False` in production |
| `DATABASE_URL` | SQLite | Full database connection URL |
| `CURRENCY_SYMBOL` | `£` | Currency symbol used in the UI |

## Running Tests

Tests use pytest with pytest-django and coverage reporting:

```bash
pytest
```

Coverage reports are written to `htmlcov/`.

## Project Structure

```
main/          # Django project settings, URLs, base views, middleware, and template tags
inventory/     # Stock management, warehouse locations, ledger, and adjustments
procurement/   # Suppliers, purchase orders, and receiving
production/    # BOM management and manufacturing jobs
sales/         # Customers, sales orders, and shipping
finance/       # Financial dashboard and ledger reporting
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

## License

MIT — see [LICENSE](LICENSE) for details.
