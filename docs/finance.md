# Finance App

Reporting module that aggregates data from the sales and procurement ledgers
into dashboards, filterable archives, CSV exports, and profitability analysis.
Ledger data originates from `SalesLedger` and `PurchaseLedger` in the sales
and procurement apps. The finance app owns a single model —
`FinanceDashboardSnapshot` — which acts as a materialized aggregation cache
so the dashboard view can serve precomputed totals instead of running
expensive aggregate queries on every request.

## Model

### `FinanceDashboardSnapshot`

Singleton row (pk=1) holding precomputed dashboard aggregates. Fields:

| Field | Type | Purpose |
|---|---|---|
| `sales_total` | `Decimal(14,2)` | All-time sales revenue |
| `purchase_total` | `Decimal(14,2)` | All-time purchase costs |
| `month_sales_total` | `Decimal(14,2)` | Current-month sales revenue |
| `month_purchase_total` | `Decimal(14,2)` | Current-month purchase costs |
| `month_year` | `PositiveSmallInt` | Year the monthly totals refer to |
| `month_month` | `PositiveSmallInt` | Month the monthly totals refer to |
| `stock_value` | `Decimal(14,2)` | Total inventory value |
| `chart_data_json` | `Text` | 12-month sales vs purchases chart (JSON) |
| `updated_at` | `DateTime` | Last refresh timestamp (auto) |

Helper methods:

* `FinanceDashboardSnapshot.load()` — returns the singleton, creating it on
  first access.
* `chart_data` property — deserialises/serialises `chart_data_json` as a
  Python dict.

## Service Layer

### `finance.services.refresh_finance_dashboard_cache()`

Recomputes all dashboard aggregates and persists them to the snapshot row:

1. All-time sales and purchase totals (`Sum` over ledgers).
2. Current-month totals (filtered by year/month).
3. 12-month chart data (`TruncMonth` + `Sum` over the last 12 calendar
   months).
4. Stock value — cheapest supplier cost per product via `Subquery`, with BOM
   component roll-up as a fallback for products without direct supplier
   pricing.

### Refresh triggers

* **Signal-based** — `post_save` on `SalesLedger`, `PurchaseLedger`, and
  `Inventory` triggers a full cache refresh via `finance.signals`. A
  thread-local re-entrancy guard prevents recursive refreshes.
* **Management command** — `python manage.py refresh_finance_cache` for
  manual or cron-based refreshes.
* **Automatic on first load** — if the snapshot row has never been populated
  or the cached month is stale (different month/year), the dashboard view
  triggers a one-time refresh before serving the page.

## Views & Templates

### Dashboard

`FinanceDashboardView` reads from the `FinanceDashboardSnapshot` cache
instead of computing aggregates per request:

* **All-time totals** — total sales revenue, total purchase costs, and gross
  profit.
* **Current month totals** — month-to-date sales, purchases, and profit.
* **Stock value** — from the cached snapshot.
* **12-month chart** — sales vs purchases by month rendered as a bar/line
  chart from the cached JSON.
* **Recent activity** — the five most recent sales ledger entries and five
  most recent purchase ledger entries (queried live with `select_related`).

### Sales Ledger

* **SalesLedgerArchiveView** — paginated list of all sales ledger entries
  (25 per page). Filterable by customer and product via GET parameters.
  Shows an overall total across all filtered results and a page total for the
  current page.
* **SalesLedgerMonthArchiveView** — monthly drill-down view showing entries
  for a specific year/month with a month total.

Both views share `SalesLedgerFilterMixin` for consistent queryset filtering
and `LedgerArchiveMixin` for common archive configuration.

### Purchase Ledger

* **PurchaseLedgerArchiveView** — paginated list of all purchase ledger
  entries (25 per page). Filterable by supplier. Shows overall and page
  totals.
* **PurchaseLedgerMonthArchiveView** — monthly drill-down with a month total
  and page total.

Both views share `PurchaseLedgerFilterMixin` for supplier-based filtering.

### Outstanding Orders Report

`OutstandingOrdersView` surfaces all open sales and purchase orders ranked by
remaining value:

* **Open sales orders** — orders with at least one incomplete line, annotated
  with an `open_value` subquery that calculates
  `sale_price × (quantity − quantity_shipped)` per line and sums across the
  order. Paginated at 15 per page with an aggregate `open_sales_value` total.
* **Open purchase orders** — same pattern using `cost × (quantity −
  quantity_received)`. Separate pagination (`po_page` parameter) with an
  `open_purchases_value` total.

### Product P&L Report

`ProductPLView` aggregates all-time sales by product and computes per-product
profitability:

* Groups `SalesLedger` entries by product to get total quantity sold and total
  revenue in a single `GROUP BY` query.
* Annotates each product with its cheapest supplier cost via a correlated
  subquery.
* Builds rows with: unit cost, sale price, margin, margin %, total sold
  quantity, total revenue, total cost, and gross profit.
* Sortable by margin %, revenue, or gross profit (default) via the `sort` GET
  parameter.
* Summary cards: total revenue, total cost, total profit, and average margin
  percentage.
* **Top-10 chart** — horizontal bar chart of the ten most profitable products
  colour-coded by margin band: green (≥ 30%), amber (≥ 10%), red (< 10%).

### CSV Export

* **SalesLedgerExportView** — exports the sales ledger as a CSV file.
  Filterable by customer, product, year, and month. Columns: Date, Customer,
  Product, Quantity, Value, Transaction (formatted as `SO00042`).
* **PurchaseLedgerExportView** — exports the purchase ledger as a CSV file.
  Filterable by supplier, year, and month. Columns: Date, Supplier, Product,
  Quantity, Value, Transaction (formatted as `PO00042`).

Both views stream the response directly with `Content-Disposition: attachment`.

## URL Patterns

| URL | View | Name |
|---|---|---|
| `/finance/` | `FinanceDashboardView` | `finance-dashboard` |
| `/finance/sales/` | `SalesLedgerArchiveView` | `sales-ledger-archive` |
| `/finance/sales/<year>/<month>/` | `SalesLedgerMonthArchiveView` | `sales-ledger-month` |
| `/finance/purchases/` | `PurchaseLedgerArchiveView` | `purchase-ledger-archive` |
| `/finance/purchases/<year>/<month>/` | `PurchaseLedgerMonthArchiveView` | `purchase-ledger-month` |
| `/finance/sales/export/` | `SalesLedgerExportView` | `sales-ledger-export` |
| `/finance/purchases/export/` | `PurchaseLedgerExportView` | `purchase-ledger-export` |
| `/finance/reports/outstanding/` | `OutstandingOrdersView` | `outstanding-orders` |
| `/finance/reports/product-pl/` | `ProductPLView` | `product-pl` |

## Notes

* All views require authentication (enforced by `LoginRequiredMiddleware`).
* Stock value calculation uses a two-pass approach: first a subquery for
  cheapest supplier cost, then a BOM component roll-up for products without
  direct supplier pricing. The result is cached in the snapshot.
* The Product P&L report computes everything in two database queries plus
  in-memory row assembly, avoiding per-product N+1 hits.
* The dashboard reads cached aggregates from `FinanceDashboardSnapshot`,
  reducing per-request query count from ~43 to ~25.

---
