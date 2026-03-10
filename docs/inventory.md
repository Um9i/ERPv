# Inventory App

This app handles the core stock management of the ERP system. It tracks
products, on-hand quantities, warehouse locations, ledger entries for all
movements, and computed requirements based on sales and production demand.

## Models

* **Product** – core entity with a unique name, optional description, image,
  sale price, and a `catalogue_item` boolean flag. When `catalogue_item` is
  set, a sale price is required; the product then appears in the public
  catalogue API for paired-instance browsing. The `unit_cost` property returns
  the cheapest supplier cost or, if no supplier exists, recursively computes
  cost from an attached Bill of Materials (BOM). The `effective_sale_price`
  property returns `sale_price` if set, otherwise falls back to the most
  recent sales order line price. The `can_produce` property checks whether
  sufficient component inventory exists for a single unit.

* **Inventory** – one-to-one with `Product`. Records `quantity`,
  `last_updated` timestamp, and caches a computed `required` quantity
  (`required_cached`) used by dashboards. The `required` property compares
  stock with allocated production jobs and open sales orders.

* **Location** – self-referential model representing a hierarchical warehouse
  structure: Warehouse → Zone → Bin. The `full_path()` method returns a
  human-readable path string (e.g. `Warehouse 1 / Zone A / Bin 3`).

* **InventoryLocation** – join table recording how many units of a product are
  held at a specific `Location`. Enforces a `unique_together` constraint on
  `(inventory, location)`. Location quantities are validated to never exceed
  `Inventory.quantity` — the sum of all `InventoryLocation` records for a
  product must remain ≤ total stock on hand.

* **StockTransfer** – records an atomic transfer of quantity between two
  locations for the same product. Either `from_location` or `to_location` may
  be null, representing unallocated stock — enabling transfers from a bin to
  unallocated or from unallocated into a bin. On save, deducts from the source
  `InventoryLocation` (or unallocated pool), adds to the destination (creating
  it if it does not exist), and writes two signed `InventoryLedger` entries
  (one negative, one positive) tagged with their respective locations.
  `Inventory.quantity` is never modified by a transfer.

* **ProductionAllocated** – helper used by `Inventory.required` to record how
  many units have been reserved for active production jobs.

* **InventoryLedger** – immutable history of all stock movements (adjustments,
  purchase receipts, sales shipments, production runs, stock transfers). Each
  entry optionally references a `Location` for bin-level traceability. Used to
  render the time-series chart and ledger table on the product detail page.

* **InventoryAdjust** – user-created adjustments to stock. Validation ensures
  you cannot subtract more than available stock (or more than a bin holds when
  a location is specified). Saving atomically updates `Inventory.quantity`,
  optionally updates the target `InventoryLocation`, creates a ledger entry
  (with location if provided), and refreshes the cached requirement.

Signals ensure an `Inventory` and a `ProductionAllocated` record exist for
each new `Product`, and that cached requirements update whenever related sales
or production lines change.

## Views & Templates

* **Product CRUD** – Create, Update, and Delete views for `Product`. The form
  exposes name, description, image upload, and sale price fields.

* **Inventory List** – searchable, paginated list of all inventory records.
  Each row shows location badges (bin name and quantity) derived from
  `InventoryLocation` records, using `prefetch_related` to avoid N+1 queries.

* **Inventory Detail** – the primary product view, combining:
  - Key metrics: in-stock quantity, sales pending, purchases incoming,
    production pending, shortage, and sale price
  - Product image and description panel with edit and adjust-quantity actions
  - Stock Locations table: assigned bins with quantities, percentage of total
    stock, edit/delete per bin, and Transfer and Assign Location actions
  - Stock Level History line chart generated from ledger entries
  - Demand Overview donut chart and Monthly Activity bar chart
  - Inventory Ledger table with running balance, location column, and
    pagination; rows link to source transactions where available

* **Inventory Adjust** – form pre-filled with the product. Optionally prompts
  for a location (filtered to bins already assigned to this product). Negative
  adjustments to a specific bin are validated against that bin's current stock.

* **Location CRUD** – Create, Update, and Delete views for `Location`. The
  list view renders the full warehouse hierarchy as an indented tree
  (Warehouse → Zone → Bin) with inline edit and delete actions.

* **InventoryLocation CRUD** – views to assign, update, and remove stock
  location assignments for a specific inventory item. The create/update form
  validates that the total allocated quantity across all bins does not exceed
  stock on hand.

* **Stock Transfer** – dedicated form scoped to a specific inventory item.
  Source location dropdown is filtered to bins that currently hold stock.
  Validates that the source bin has sufficient quantity and that source ≠
  destination. The atomic save updates both `InventoryLocation` records and
  writes two ledger entries.

* **Dashboard** – comprehensive stock health overview:
  - Global totals: product count, total quantity, stock value (using cheapest
    supplier cost with BOM cost fallback)
  - Low-stock count and percentage of total products
  - Stock health distribution: low stock, zero stock, dead stock (quantity
    > 0, no demand, no movement in 90 days), and healthy buckets
  - Top 5 most-needed items with fill-percentage progress bars
  - 30-day stock IN/OUT movement trends with comparison arrows against the
    prior 30-day period
  - When `?required=1`, enriches context with low-stock items including
    production and purchase order coverage for suggested actions

* **Low Stock List** – paginated list of all products where `required_cached`
  > 0, with supplier and BOM context, filterable by purchasable or producible,
  and links to pre-populated purchase order creation.

* **Catalogue API** – `CatalogueApiView` returns catalogue products as JSON.
  Requires Bearer token authentication matching a `PairedInstance.our_key`.
  Returns product name, description, sale price, and SKU for products with
  `catalogue_item=True` and a sale price set.

## Key Features

* Hierarchical warehouse locations with enforced quantity integrity
* Atomic stock transfers with dual ledger entries and location tagging,
  including transfers from and to unallocated stock
* Location-aware inventory adjustments with bin-level validation
* Full audit ledger with running balance and location column
* Indexed fields on all frequently-filtered columns
* Cached aggregate (`required_cached`) to avoid expensive per-request queries
* Cross-app dependencies: inventory queries sales, procurement, and production
  for pending figures
* Chart.js visualisations on dashboard and detail pages
* Stock health dashboard with dead stock detection and 30-day trend analysis
* Catalogue API endpoint for paired-instance product browsing
* Authentication enforced via middleware; all views require login
