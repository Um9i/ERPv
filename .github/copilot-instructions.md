# ERPv — Copilot Instructions

> Auto-loaded by VS Code Copilot on every conversation.
> For deep architectural context, read `zDoc/CLAUDE_CONTEXT.md` before any major feature work.

## Project Identity

ERPv is a **Django 6.0.3 / Python 3.14** ERP for small-to-medium manufacturing and distribution.
8 Django apps, ~40 models, 650+ tests (86% coverage, 85% CI threshold), Bootstrap 5 frontend.
Live demo: https://um9i.dev/ — License: MIT.

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

## Critical Conventions

1. **All writes use `@transaction.atomic`** — especially `Production.save()`, `StockTransfer.save()`, `SalesOrderShipView`, `InventoryAdjust.save()`
2. **Audit fields** — `created_by`/`updated_by` FK via `AuditMixin` on orders, adjustments, transfers; `AuditLog` model for field-level price/cost changes
3. **Signal-driven cache** — `post_save` on `SalesLedger`, `PurchaseLedger`, `Inventory` triggers `refresh_finance_dashboard_cache()` with re-entrancy guard
4. **Singleton models** — `FinanceDashboardSnapshot` (pk=1) and `CompanyConfig` (pk=1) use `.load()` class method
5. **Soft deletes** — `SoftDeleteMixin` on Product, Supplier, PurchaseOrder, Customer, SalesOrder, Production
6. **API auth** — Bearer token validated via `hmac.compare_digest()` against `PairedInstance.our_key`; CSRF exempt only on machine-to-machine endpoints
7. **Permissions** — `PermissionRequiredMixin` with 12 custom permissions; `LoginRequiredMiddleware` on all views
8. **Rate limiting** — `django-ratelimit` on all API views (60/m) and login (10/m POST)

## Developer Preferences

- Use `.venv` virtualenv
- Run `ruff` and `mypy` after changes (`make check`)
- **Do NOT run tests** — hand that off to the user
- Keep `docs/`, `README.md`, `TODO.md`, and `templates/home.html` updated with relevant changes
- Read `zDoc/CLAUDE_CONTEXT.md` for full context before major changes
- Place tests in `tests/` directory with `@pytest.mark.unit`, `integration`, or `e2e` markers
- Use factories from `main/factories.py`

## Quality Gate

```bash
make check          # ruff format + lint + tsc
make mypy           # type check all modules
make test           # parallel tests (~12s) — user runs this
make test-coverage  # HTML coverage report
make audit          # bandit + pip-audit
```

## Self-Improvement Protocol

After completing significant work in this project, update `zDoc/CLAUDE_CONTEXT.md`:
- Append a dated entry to the **Session Log** section
- Update **Known Gaps** when items are completed or new ones discovered
- Update **Architectural Patterns** if new patterns are introduced
- Flag any documentation drift (e.g., README claims X but code does Y)
