# Inventory App

This app handles the core stock management of the ERP system.  It keeps track
of products, on‑hand quantities, ledger entries for adjustments, and computed
requirements based on sales and production.

## Models

* **Product** – simple entity with a unique name.  The `unit_cost` property
  returns the cheapest supplier cost or, if no supplier exists, recursively
  computes cost from an attached Bill of Materials (BOM).

* **Inventory** – one‑to‑one with `Product`.  Records `quantity`, `last_updated`
  timestamp and caches a computed `required` quantity (`required_cached`) used
  by dashboards.  The `required` property compares stock with allocated
  production jobs and open sales orders.

* **ProductionAllocated** – helper used by `Inventory.required` to record how
  many units have been reserved for active production jobs.

* **InventoryLedger** – immutable history of all movements (adjustments,
  purchase, sales, etc.).  Used to render the time‑series chart on the product
  detail page.

* **InventoryAdjust** – user‑created adjustments to stock.  Validation ensures
  you cannot subtract more than available, and saving automatically updates the
  linked `Inventory` record, creates a ledger entry, and refreshes the cached
  requirement.

Signals ensure an `Inventory` and a `ProductionAllocated` record exist for each
new `Product`, and that cached requirements update whenever related sales or
production lines change.

## Views & Templates

* **List / Detail / Create / Update / Delete** views for `Product` and
  inventory adjustments.  List pages support simple search and pagination; the
  inventory detail combines:
  * current quantity and last‑updated timestamp
  * pending activity card with a bar chart (sales, purchase, production,
    shortage)
  * ledger table with pagination
  * time‑series line chart generated from ledger entries
  * computed context values such as `sales_pending`, `purchase_pending` and
    `production_pending` using aggregated queries across other apps.

* Adjust form auto‑fills and hides product selection and checks `complete` on
  submission.

* Dashboard view aggregates global totals (product count, total quantity,
  stock value using `unit_cost`).  Links allow navigation to the full inventory
  list.

## Key Features

* Indexed fields on models for performant filtering
* Caching of computed aggregates to avoid expensive queries
* Cross‑app dependencies: inventory queries sales, procurement, and production
  for pending figures
* Authentication enforced via middleware; all views require login except home
  and registration
* Chart.js used for visualizations on dashboard and detail pages

---
