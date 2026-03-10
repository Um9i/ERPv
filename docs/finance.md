# Finance App

Read-only reporting module that aggregates data from the sales and procurement
ledgers into dashboards, filterable archives, CSV exports, and profitability
analysis. The finance app has no models of its own — it queries `SalesLedger`
and `PurchaseLedger` from the sales and procurement modules respectively.

## Views & Templates

### Dashboard

`FinanceDashboardView` presents the top-level financial overview:

* **All-time totals** – total sales revenue, total purchase costs, and gross
  profit derived from the ledgers.
* **Current month totals** – month-to-date sales, purchases, and profit.
* **Stock value** – computed from inventory quantities multiplied by the
  cheapest supplier cost per product, with BOM cost roll-up as a fallback for
  products that have no direct supplier pricing.
* **12-month chart** – sales vs purchases by month rendered as a bar/line
  chart from aggregated `TruncMonth` queries.
* **Recent activity** – the five most recent sales ledger entries and five
  most recent purchase ledger entries.

### Sales Ledger

* **SalesLedgerArchiveView** – paginated list of all sales ledger entries
  (25 per page). Filterable by customer and product via GET parameters.
  Shows an overall total across all filtered results and a page total for the
  current page.
* **SalesLedgerMonthArchiveView** – monthly drill-down view showing entries
  for a specific year/month with a month total.

Both views share `SalesLedgerFilterMixin` for consistent queryset filtering
and `LedgerArchiveMixin` for common archive configuration.

### Purchase Ledger

* **PurchaseLedgerArchiveView** – paginated list of all purchase ledger
  entries (25 per page). Filterable by supplier. Shows overall and page
  totals.
* **PurchaseLedgerMonthArchiveView** – monthly drill-down with a month total
  and page total.

Both views share `PurchaseLedgerFilterMixin` for supplier-based filtering.

### Outstanding Orders Report

`OutstandingOrdersView` surfaces all open sales and purchase orders ranked by
remaining value:

* **Open sales orders** – orders with at least one incomplete line, annotated
  with an `open_value` subquery that calculates
  `sale_price × (quantity − quantity_shipped)` per line and sums across the
  order. Paginated at 15 per page with an aggregate `open_sales_value` total.
* **Open purchase orders** – same pattern using `cost × (quantity −
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
* **Top-10 chart** – horizontal bar chart of the ten most profitable products
  colour-coded by margin band: green (≥ 30%), amber (≥ 10%), red (< 10%).

### CSV Export

* **SalesLedgerExportView** – exports the sales ledger as a CSV file.
  Filterable by customer, product, year, and month. Columns: Date, Customer,
  Product, Quantity, Value, Transaction (formatted as `SO00042`).
* **PurchaseLedgerExportView** – exports the purchase ledger as a CSV file.
  Filterable by supplier, year, and month. Columns: Date, Supplier, Product,
  Quantity, Value, Transaction (formatted as `PO00042`).

Both views stream the response directly with `Content-Disposition: attachment`.

## URL Patterns

| URL | View | Name |
|---|---|---|
| `/finance/` | `FinanceDashboardView` | `finance-dashboard` |
| `/finance/sales/` | `SalesLedgerArchiveView` | `salesledger-archive` |
| `/finance/sales/<year>/<month>/` | `SalesLedgerMonthArchiveView` | `salesledger-month` |
| `/finance/purchases/` | `PurchaseLedgerArchiveView` | `purchaseledger-archive` |
| `/finance/purchases/<year>/<month>/` | `PurchaseLedgerMonthArchiveView` | `purchaseledger-month` |
| `/finance/sales/export/` | `SalesLedgerExportView` | `salesledger-export` |
| `/finance/purchases/export/` | `PurchaseLedgerExportView` | `purchaseledger-export` |
| `/finance/reports/outstanding/` | `OutstandingOrdersView` | `outstanding-orders` |
| `/finance/reports/product-pl/` | `ProductPLView` | `product-pl` |

## Notes

* All views require authentication (enforced by `LoginRequiredMiddleware`).
* The module deliberately avoids its own model layer — all data originates
  from ledger entries written by the sales and procurement apps during their
  shipment and receiving workflows.
* Stock value calculation uses a two-pass approach: first a subquery for
  cheapest supplier cost, then a BOM component roll-up for products without
  direct supplier pricing.
* The Product P&L report computes everything in two database queries plus
  in-memory row assembly, avoiding per-product N+1 hits.

---
