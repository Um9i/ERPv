# Production App

Supports bill‑of‑materials (BOM) management and tracking of production jobs.

## Core Models

* **BillOfMaterials** – associates a finished `Product` with component
  `Products` via BOM items.
* **BOMItem** – line items for a BOM, recording component product and quantity.
* **Production** – represents a manufacturing job for a particular product.
  It stores the quantity to be made, how many units have been received (i.e. a
  job may be produced in batches), and flags for `complete` and `closed`.
  Production saving logic validates received quantities against the ordered
  amount and updates associated `InventoryLedger` entries (handled in
  `models.py`).

## Features & Views

### BOM Management

* CRUD views for BOMs and BOM items.  List views offer search and pagination,
  detail pages show component lists with their own pagination.
* The BOM `create/update` forms now embed an inline formset for
  `BOMItem` lines, allowing multiple components to be added or edited directly
  on the same page.  A small Javascript helper replicates the last row so the
  user can click "Add another component" to generate a new blank line.  The
  finished product field may still be pre‑populated/hidden via query
  parameters as before.

### Production Jobs

* `ProductionCreateView` and `UpdateView` allow starting and editing jobs.
  Only products with an existing BOM may be selected (with the exception of an
  existing job whose BOM has since been removed).
* List and search pages for jobs and APIs (`ProductionListApiView`) to serve
  incomplete jobs in JSON – used by dashboard widgets or external consumers.
* Detail pages display job metadata and associated BOM.
* `ProductionDetailView` supports a "complete production" action which marks
  the job complete without adjusting inventory; actual stock changes occur via
  the receiving flow.

### Receiving Flow

* `ProductionReceivingListView` shows open jobs with search and pagination.
* `ProductionReceiveView` accepts a quantity (or "receive all") and updates
  the `quantity_received` field.  Received quantities are sanitized to ensure
  they do not exceed the remaining amount; validation errors during save are
  displayed via Django messages.
* Jobs can be partially received over time; once the received amount meets the
  ordered quantity the job becomes complete (triggering inventory/l edger
  updates via model logic).

### Dashboard

`ProductionDashboardView` summarizes:

* total number of BOMs defined
* count of active (not closed) production jobs
* count of completed jobs

These metrics are rendered as cards with links to appropriate lists.

## Additional Notes

* The production logic is tightly coupled to inventory via ledger entries
  created when jobs are marked complete or received.  The `Production.save`
  method contains validation to avoid negative inventory and maintains cache
  values in `Inventory` where necessary.
* All views require authentication; UI features are limited accordingly.
* There is an AJAX‑style API for fetching open jobs, used by the front end for
  quick lookups (e.g. auto‑populating receive forms).

---
