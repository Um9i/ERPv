# Production App

Supports bill-of-materials (BOM) management, production job planning, and
manufacturing lifecycle tracking including component shortage analysis, cost
roll-up, and bin-level receiving of finished goods.

## Core Models

* **BillOfMaterials** – associates a finished `Product` with its component
  `Product`s via BOM items. One-to-one with `Product`.

* **BOMItem** – line items for a BOM, recording the component product and
  quantity per unit of the finished product. `clean()` prevents self-referential
  BOMs and detects circular references using an iterative traversal of the
  full component tree.

* **Production** – represents a manufacturing job for a specific product.
  Stores the ordered quantity, units received (`quantity_received`), due date,
  and flags for `complete`, `closed`, `bom_allocated`, and
  `bom_allocated_amount`. Key properties:
  - `remaining` – units not yet received
  - `status` – derived human-readable status: Open, Allocated, Completing,
    or Closed
  - `materials_available` – whether current inventory covers the full job qty
  - `materials_available_for_remaining` – whether inventory covers remaining qty
  - `order_number` – zero-padded reference e.g. `PR00042`

  The `save()` method is fully atomic and handles: BOM component allocation
  (incrementing `ProductionAllocated`), inventory deduction of components on
  receive, finished goods increment, ledger entry creation for all affected
  products, job closure when fully received, and cache refresh for all affected
  inventory records.

  The `cancel()` method releases any outstanding allocated component quantities
  and closes the job without affecting received inventory.

## Services

* **`build_bom_tree(product, quantity, visited)`** – recursively builds a
  serialisable tree structure from a product's BOM, scaling quantities down
  each level (`item.quantity × parent_quantity`). Each node carries `id`,
  `name`, `quantity`, `stock`, `sufficient` (bool), and `children`. Includes a
  circular reference guard via an immutable `visited` set copied per branch.
  Missing `Inventory` records are treated as `stock=0`. Used by both the BOM
  detail view and the production detail view to drive the interactive BOM
  visualiser.

* **`receive_production_into_location(job, quantity, location)`** – atomic
  transaction that updates `job.quantity_received`, calls `Production.save()`
  (firing all allocation, ledger, and closure logic), routes the finished
  goods delta to the specified `InventoryLocation` (creating it if it doesn’t
  exist), and tags the finished-goods `InventoryLedger` entry with the
  destination location.

* **`bom_product_ids()`** – returns the set of product IDs that have a
  `BillOfMaterials` attached.

* **`pending_jobs_by_product()`** – returns a dict of product ID → remaining
  quantity on active (non-closed) production jobs.

## Features & Views

### BOM Management

* CRUD views for BOMs and BOM items. List views support search and pagination.
* BOM detail pages show component lists, link to product inventory, and render
  the full BOM tree via `build_bom_tree()` with unit cost, component cost,
  sale price, and margin percentage calculations.
* The BOM create/update forms embed an inline formset for `BOMItem` lines,
  allowing multiple components to be added or edited on a single page. A
  JavaScript helper replicates the last row for "Add another component"
  functionality. The finished product field can be pre-populated via query
  parameters.

### Production Jobs

* `ProductionCreateView` and `UpdateView` for starting and editing jobs.
  Only products with an existing BOM may be selected.
* List view with search, status filter, and pagination. Bulk N+1 mitigation
  pre-loads BOM items and inventory to compute a materials-ok flag in a single
  pass. Each row shows:
  - Due date badge colour-coded by urgency (red = overdue, amber = due within
    7 days, muted = on track, dash = no date)
  - Sufficient Materials indicator (green check or red warning triangle)
    reflecting `materials_available_for_remaining`
* Jobs are ordered by: open first, then due date ascending (nulls last), then
  newest first — surfacing the most urgent work at the top.

### Production Detail

The detail page combines:

* **Job metadata** – product, quantity, remaining, status, due date, created
  and updated timestamps
* **Cost Summary** – rendered when unit cost or sale price is available:
  - Unit Cost and Sale Price per unit
  - Total Job Cost (`unit_cost × quantity`) and Projected Value
    (`sale_price × quantity`) with Projected Margin %
  - Produced Cost and Produced Value for received units with Actual Margin %
  - Margin percentages colour-coded: green ≥ 30%, amber ≥ 10%, red < 10%
  - Section hidden entirely when both unit cost and sale price are zero
* **Shortage alert banner** – shown when any component has insufficient stock
  for the remaining quantity, with a link to the inventory low-stock view
* **Interactive BOM Visualiser** – collapsible tree rendered client-side from
  JSON context data. Each node shows a toggle chevron, green check or red ✗
  status icon, product name, `Need: N` quantity (scaled to job remaining), and
  `Stock: N` value. An Expand All button opens the full tree. Root node uses
  `job.remaining` as the base quantity.
* **Component Breakdown table** – flat tabular view of direct BOM components
  with per-unit quantity, required (remaining), in-stock, and shortfall
  columns. Rows with shortfalls are highlighted red.
* **Action buttons** – Receive Units and Cancel Job

### Receiving Flow

* `ProductionReceiveView` presents a form with quantity to receive (defaulting
  to remaining) and an optional Location dropdown (all configured locations).
* When a location is selected, receiving is handled by
  `receive_production_into_location()` in `services.py`, which:
  1. Updates `job.quantity_received` and calls `Production.save()` — all
     existing BOM deduction, ledger, allocation, and closure logic fires
  2. Routes the finished goods delta to the specified `InventoryLocation`
     (creating it if it doesn't exist)
  3. Tags the finished-goods `InventoryLedger` entry with the destination
     location
* When no location is selected, falls back to calling `Production.save()`
  directly — existing behaviour, no location recorded.
* Partial receiving is supported; jobs close automatically when
  `quantity_received >= quantity`.

### Dashboard

`ProductionDashboardView` summarises:
* Total BOMs defined
* Count of active (not closed) production jobs and jobs due today or earlier
* Count of completed jobs and completion rate percentage
* Producible items: products with a shortage and a BOM that are not yet fully
  covered by active production jobs, with links to create new jobs

Rendered as metric cards with links to the appropriate lists.

### Production Schedule (Dashboards App)

`ProductionScheduleView` provides a day-based production schedule driven by
`Production.due_date`, consistent with the Shipping and Delivery Schedule
dashboards:
* Week navigation bar with daily links and job counts for non-closed jobs
* Jump to Today button when viewing a different date
* Overdue production jobs section (red border, critical) for non-closed jobs
  past their due date
* Production Jobs table for the selected date showing Job #, Product, Status,
  Quantity, and Remaining
* HTMX partial updates every 30 seconds via `_production_metrics.html`
* 5-minute cache with `vary_on_headers("HX-Request")`

## Key Features

* Fully atomic `Production.save()` covering allocation, receiving, ledger,
  and cache in a single database transaction
* Recursive BOM cost roll-up via `Product.unit_cost` with iterative cycle
  detection
* Per-job margin analysis using `effective_sale_price` (sale price or last
  sold price)
* Interactive BOM visualiser with live stock state and quantity scaling,
  shared between BOM detail and production detail views
* Due date urgency system with colour-coded list view badges
* Bin-level finished goods receiving integrated with inventory location system
* Component shortage warnings at both list and detail level
* Bulk N+1 query mitigation on the production list view
* Dashboard with producible-item suggestions and due-date awareness
* All views require authentication

## Notifications

* **Material shortage on job creation** — when a production job is created
  and any BOM component has insufficient inventory for the job quantity, all
  active users receive a `LOW_STOCK` / `WARNING` notification.  The message
  lists each short component with the deficit and whether it can be produced
  (has its own BOM) or must be procured.  The notification links to the
  production job detail page.
