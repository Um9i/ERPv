# ERPv — Copilot Instructions

> Canonical AI context file — auto-loaded by VS Code Copilot on every conversation.
> `zDoc/CLAUDE_CONTEXT.md` is now deprecated; this is the single source of truth.

---

## Project Identity

ERPv is a **Django 6.0.3 / Python 3.14** ERP for small-to-medium manufacturing and distribution.
8 Django apps, ~40 models, 650+ tests (86% coverage, 85% CI threshold), Bootstrap 5 frontend.
Live demo: https://um9i.dev/ — License: MIT.

---

## App Structure

| App | Owns | Key Patterns |
|-----|------|-------------|
| `inventory` | Product, Inventory, Location, StockTransfer, InventoryLedger, InventoryAdjust | Hierarchical locations, atomic transfers, cached `required_cached` |
| `procurement` | Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseLedger, PO Templates | Scan-to-store, receiving workflow, remote PO→SO forwarding |
| `production` | BillOfMaterials, BOMItem, Production, ProductionLedger | Recursive BOM with cycle detection, fully atomic `Production.save()` |
| `sales` | Customer, SalesOrder, SalesOrderLine, SalesLedger, PickList | Scan-to-pick, location-aware shipments, PDF invoices (WeasyPrint) |
| `finance` | FinanceDashboardSnapshot (singleton pk=1) | Signal-based cache refresh, CSV export, Product P&L |
| `config` | CompanyConfig, PairedInstance, Notification, WebhookEndpoint | Multi-site pairing, Bearer token auth, HMAC webhooks |
| `dashboards` | No models (view-only) | Shipping/delivery/production schedules, HTMX partial updates |
| `main` | AuditLog, middleware, template tags, factories | Settings, URL routing, `SoftDeleteMixin`, `AuditMixin`, `safe_redirect()` |

---

## Architectural Patterns

### 1. Atomic Transactions
Every write that touches multiple tables uses `@transaction.atomic`. Key examples:
- **`Production.save()`** — allocates BOM components → deducts inventory → creates ledger entries → closes job → refreshes caches
- **`StockTransfer.save()`** — deducts from source `InventoryLocation` → adds to destination → writes two signed `InventoryLedger` entries
- **`SalesOrderShipView`** — `select_for_update()` for race-condition safety → deducts from allocated bins → creates sales ledger entries
- **`InventoryAdjust.save()`** — validates bin stock → updates `Inventory.quantity` + `InventoryLocation` → creates ledger entry → refreshes cache

### 2. Signal-Driven Cache
`FinanceDashboardSnapshot` (singleton pk=1) holds precomputed aggregates (totals, stock value, 12-month chart JSON). Refreshed by `post_save` on `SalesLedger`, `PurchaseLedger`, `Inventory`. Thread-local re-entrancy guard prevents recursive refreshes. Also: `python manage.py refresh_finance_cache`.

### 3. Recursive BOM with Cycle Detection
- `BOMItem.clean()` prevents self-referential/circular BOMs via iterative traversal
- `build_bom_tree()` service builds a serialisable tree, scaling quantities per-level with an immutable `visited` set per branch
- `Product.unit_cost` computes cost from cheapest supplier OR recursive BOM rollup

### 4. Scan Workflows
- **Scan-to-Store** (procurement): Scanner UI → match PO line by barcode/SKU → confirm → `store_confirmed` flag + timestamp → `all_store_confirmed` on PO
- **Scan-to-Pick** (sales): Scanner UI → match `PickListLine` → confirm → "Proceed to Ship" when all non-shortage lines confirmed

### 5. Multi-Site Pairing
`PairedInstance` stores remote URL + API keys (Bearer token via `hmac.compare_digest`). Catalogue API, PO→SO forwarding, and cost update notifications all use this.

### 6. Singleton Models
`FinanceDashboardSnapshot` (pk=1) and `CompanyConfig` (pk=1) — both use `.load()` class method, created on first access.

### 7. Soft Deletes
`SoftDeleteMixin` in `main/mixins.py` with custom managers. Applied to: Product, Supplier, PurchaseOrder, Customer, SalesOrder, Production. Soft-deleted records excluded from default querysets.

### 8. Audit Trail
- **Field-level**: `AuditMixin` adds `created_by`/`updated_by` FK to orders, adjustments, transfers
- **Change-level**: `AuditLog` records price/cost field changes with old/new values

### 9. Permission System
12 custom permissions across all apps, enforced via `PermissionRequiredMixin`. `LoginRequiredMiddleware` catches everything else. `assign_permissions` management command for setup.

### 10. DRF for Machine-to-Machine APIs
`APIView` + `BearerTokenAuthentication` (`main/auth.py`) for all Bearer-auth M2M endpoints. Internal AJAX endpoints (session-auth) remain plain Django views. OpenAPI 3.0 via `drf-spectacular`; Swagger UI at `/api/docs/`.

---

## Database Schema Summary

### Inventory
- **Product** → name, sku, barcode, sale_price, catalogue_item, image; `unit_cost`, `effective_sale_price`, `can_produce`
- **Inventory** → 1:1 Product; quantity, `required_cached` (allocated production + open SO demand)
- **Location** → self-referential hierarchy (Warehouse → Zone → Bin); `full_path()`
- **InventoryLocation** → join table with unique constraint; quantities ≤ total stock
- **StockTransfer** → atomic between locations, nullable from/to for unallocated pool
- **InventoryLedger** → immutable history; Action enum: PO, SO, Production, Adjustment, Transfer, Seed
- **InventoryAdjust** → user-created, location-optional, validates against bin/total stock
- **ProductionAllocated** → tracks reserved BOM components per production job

### Procurement
- **Supplier** → soft-deletable; **SupplierProduct** → supplier→product with cost
- **PurchaseOrder** → cached `total_amount`, `all_store_confirmed`; soft-deletable
- **PurchaseOrderLine** → qty, received, `store_confirmed` + `store_confirmed_at`
- **PurchaseLedger** → historical receipts
- **PurchaseOrderTemplate / PurchaseOrderTemplateLine** → reusable PO templates

### Sales
- **Customer** → soft-deletable; **CustomerProduct** → customer→product with price
- **SalesOrder** → cached `total_amount`, `ship_by_date`; soft-deletable
- **SalesOrderLine** → qty, shipped, auto-completes on full shipment
- **SalesLedger** → historical shipment records
- **PickList** → `generate_for_order()`, `refresh()`, `_populate_lines()`
- **PickListLine** → pick instruction with optional location, `is_shortage`, `confirmed`

### Production
- **BillOfMaterials** → 1:1 Product; `production_cost`
- **BOMItem** → component + quantity; circular reference validation in `clean()`
- **Production** → `remaining`, `status` (Open→Allocated→Completing→Closed), `materials_available`; soft-deletable
- **ProductionLedger** → historical cost record

### Finance
- **FinanceDashboardSnapshot** → singleton (pk=1); all-time/monthly totals, stock value, chart JSON

### Config
- **CompanyConfig** → singleton (pk=1); branding, VAT, email settings
- **PairedInstance** → remote URL + `api_key`/`our_key` for Bearer auth
- **Notification** → user-scoped; categories: LOW_STOCK, ORDER_OVERDUE, ORDER_STATUS, PRICE_UPDATE
- **WebhookEndpoint** → external subscriptions with HMAC-SHA256 secret; **WebhookDelivery** → delivery log

### Main
- **AuditLog** → field-level change tracking (old/new values)

---

## URL Map (Summary)

| Prefix | Key Endpoints |
|--------|--------------|
| `/inventory/` | Dashboard, product CRUD/detail, adjust, locations, transfers, low-stock, catalogue API |
| `/procurement/` | Dashboard, supplier CRUD, PO CRUD/receive/scan-store, PO templates, supplier-product API |
| `/sales/` | Dashboard, customer CRUD, SO CRUD/ship/invoice, pick lists, scan-pick, notify API |
| `/production/` | Dashboard, BOM CRUD, job list/detail, receive |
| `/finance/` | Dashboard, sales/purchase ledgers + CSV export, outstanding report, product P&L |
| `/config/` | Company config, paired instances, notifications, webhooks |
| `/dashboards/` | Shipping/delivery/production schedules (HTMX partials) |
| `/api/docs/` | Swagger UI; `/api/schema/` raw OpenAPI schema |

---

## Critical Conventions

1. **All writes use `@transaction.atomic`** — especially `Production.save()`, `StockTransfer.save()`, `SalesOrderShipView`, `InventoryAdjust.save()`
2. **Audit fields** — `created_by`/`updated_by` FK via `AuditMixin`; `AuditLog` for field-level price/cost changes
3. **Signal-driven cache** — `post_save` on `SalesLedger`, `PurchaseLedger`, `Inventory` → `refresh_finance_dashboard_cache()` with re-entrancy guard
4. **Singleton models** — `FinanceDashboardSnapshot` and `CompanyConfig` use `.load()` class method
5. **Soft deletes** — `SoftDeleteMixin` on 6 critical models
6. **API auth** — Bearer token via `hmac.compare_digest()` against `PairedInstance.our_key`; CSRF exempt only on M2M endpoints
7. **Permissions** — `PermissionRequiredMixin` with 12 custom permissions; `LoginRequiredMiddleware` on all views
8. **Rate limiting** — `django-ratelimit` on all API views (60/m) and login (10/m POST)

---

## Developer Preferences

- Use `.venv` virtualenv (`PYTHON = .venv/bin/python` in Makefile)
- Run `ruff` and `mypy` after changes (`make check` + `make mypy`)
- **Do NOT run tests** — hand that off to the user
- Keep `docs/`, `README.md`, `TODO.md`, and `templates/home.html` updated with relevant changes
- Place tests in `tests/` with `@pytest.mark.unit`, `integration`, or `e2e` markers
- Use factories from `main/factories.py`; fixtures in `tests/conftest.py`

## Quality Gate

```bash
make check          # ruff format + lint + tsc
make mypy           # type check all modules
make test           # parallel pytest (~12s) — user runs this
make test-coverage  # HTML coverage report
make audit          # bandit + pip-audit
```

---

## Testing Conventions

- **Framework**: pytest + pytest-django + factory_boy + Faker; parallel via pytest-xdist
- **Coverage**: 86% actual, 85% CI threshold (`--cov-fail-under=85` in `pytest.ini`)
- **Fixtures** (conftest.py): `db`, `client`, `user`, `staff_user`, `product`, `supplier`, `customer`, `sales_order`, `purchase_order`, `bom_with_items`

---

## Deployment & Environment

- **Docker**: `python:3.14-slim` base; `development` stage (includes dev deps + `runserver`); `production` stage (gunicorn, collectstatic baked in)
- **Compose**: `docker-compose.yml` (dev, postgres:17, healthcheck), `docker-compose.prod.yml` (resource limits, JSON logging)
- **Server**: Gunicorn 3 workers; WhiteNoise for static files (compressed manifest in prod)
- **Health check**: GET `/healthz/` — checks DB connectivity

| Variable | Default | Required |
|----------|---------|----------|
| `SECRETKEY` | — | Yes (prod) |
| `DEBUG` | `False` | No |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | No |
| `DATABASE_URL` | SQLite fallback | Yes (prod) |
| `CURRENCY_SYMBOL` | `£` | No |
| `SENTRY_DSN` | — | No (enables Sentry) |
| `CORS_ALLOWED_ORIGINS` | — | No |
| `CSRF_TRUSTED_ORIGINS` | — | No |
| `EMAIL_*` | — | No (enables email) |
| `LOG_LEVEL` | — | No |

---

## Known Gaps & Active Roadmap

> Update when items are completed. Full history in `TODO.md`.

- [ ] Code quality — 43 issues (N+1 queries, DRY, clarity, SoC, type safety) catalogued in `TODO.md` — see Code Quality Findings section
- [ ] Automated purchasing — reorder points, auto-PO generation
- [ ] Advanced analytics — inventory turnover, supplier scoring, CLV, KPI dashboard
- [ ] Lot/batch tracking — traceability and recall management
- [ ] Returns management — RMA workflow, credit/debit notes
- [ ] Deployment documentation — `docs/deployment.md`
- [ ] i18n — `gettext_lazy`, locale config, language selector
- [ ] ER diagram — `django-extensions graph_models`
- [ ] Container image scanning in CI — Trivy/Grype
- [ ] Multi-tenant — `company_id` FK on transactional models

### Documentation Gaps
- Webhook API not formally documented (6 event types, HMAC-SHA256 payloads)
- PDF invoice template path and customisation not documented
- No architecture diagram (DB relationships, app dependencies)

---

## Self-Improvement Protocol

After completing significant work (new features, refactors, bug fixes spanning multiple files), append a dated entry to the **Session Log** below.

**Log:** date, summary, new patterns, mistakes resolved, docs drift found, gaps completed/discovered.
**Update:** move completed Known Gaps to Completed table; add new patterns to Architectural Patterns; flag any inconsistency with `docs/`.
**Don't:** rewrite existing entries; remove historical entries; log trivial changes.

### Completed Gaps

| Date | Item | Notes |
|------|------|-------|
| Pre-2026-03 | Rate limiting | `django-ratelimit` on all API views + login |
| Pre-2026-03 | Role-based permissions | 12 custom permissions, `PermissionRequiredMixin` |
| Pre-2026-03 | Soft deletes | `SoftDeleteMixin` on 6 critical models |
| Pre-2026-03 | Sentry integration | Gated by `SENTRY_DSN` |
| Pre-2026-03 | Webhook retry logic | Exponential backoff (2s, 4s, 8s), 3 retries |
| Pre-2026-03 | N+1 fixes (dashboard) | Annotated queries in all 3 schedule views |
| Pre-2026-03 | CI coverage threshold | 85% via `--cov-fail-under` |
| 2026-03-22 | Accessibility (WCAG 2.1 AA) | Skip link, ARIA, `scope="col"`, form aria-*, focus-visible |
| 2026-03-22 | API Documentation (OpenAPI) | `drf-spectacular` + DRF; `BearerTokenAuthentication`; `docs/api.md` |

---

## Session Log

> Append new entries below. Most recent at the bottom.

### 2026-03-16 — Initial Context Document Creation
Created `zDoc/CLAUDE_CONTEXT.md` and updated `.github/copilot-instructions.md`. Collated all project docs into a single searchable reference. 9 core architectural patterns documented.

### 2026-03-22 — Accessibility (WCAG 2.1 AA)
Comprehensive WCAG 2.1 AA pass across 114 templates. Added `.visually-hidden`, `scope="col"` on 318 `<th>`, `aria-label` on icon-only buttons, `aria-hidden` on decorative icons, `aria-describedby`/`aria-invalid` on forms, `role="contentinfo"` on footer, `focus-visible` styles. 30 accessibility tests added.

### 2026-03-22 — API Documentation (DRF + drf-spectacular)
Integrated DRF 3.17 + drf-spectacular 0.29. Migrated 6 M2M endpoints to `APIView` + serializers. New `BearerTokenAuthentication` in `main/auth.py`. Fixed timing-attack vulnerability in two notify views. Added missing rate limits. `docs/api.md` created.

### 2026-06-13 — Docker Migration & Build Optimisation
Migrated from Podman to Docker throughout. Added BuildKit cache mounts (`apt`, `pip`, `npm`). Added `development` Docker stage (installs `requirements-dev.txt`, uses `runserver`). Pinned `postgres:17`. Added `healthcheck` on db; `depends_on: condition: service_healthy`. Removed Podman SELinux `:Z`/`:z` volume flags. Added retry cap to entrypoint wait loop.

### 2026-06-13 — Context Consolidation
Merged `zDoc/CLAUDE_CONTEXT.md` into `.github/copilot-instructions.md` as the single canonical AI context file. Cleaned up `TODO.md` to remove completed items and instructions. `zDoc/CLAUDE_CONTEXT.md` is now deprecated.
