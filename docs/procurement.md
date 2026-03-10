# Procurement App

This app manages suppliers, supplier‑product relationships, purchase orders,
receiving and dashboard metrics.

## Models Overview

* **Supplier** with name and contact details.  Many‑to‑one relationships to
  `SupplierProduct` and `PurchaseOrder`.
* **SupplierContact** for tracking individuals associated with a supplier.
* **SupplierProduct** links a supplier to a catalogue `Product` with a cost.
  Used when creating purchase orders so the correct supplier price is applied.
* **PurchaseOrder** and **PurchaseOrderLine** model an order and its line items.
  Order lines record quantities, received amounts, completion status, and
  stored value once fully received.  Saving a line triggers inventory and
  purchase ledger updates.
* **PurchaseLedger** (in models) keeps a history of receipts for reporting.

Indexed fields on frequently queried columns allow efficient lookups and
reporting.

## Views & Workflows

* CRUD views for suppliers, contacts, and supplier products with standard
  forms (rendered via crispy‑forms with the `bootstrap5` pack).  List pages
  implement search and pagination.  Detail pages for suppliers display
  paginated lists of their products, orders and contacts.
* **SupplierProductIDsView** returns JSON of supplier‑product IDs – used by
  client‑side JS on the order form to limit drop‑down choices.
* Purchase order creation uses an inline formset for lines.  Forms may be
  prefilled with a supplier via query string; product fields are filtered to
  that supplier’s catalogue.
* Order list and receiving list views support searching by supplier name or
  primary key, and paginate results.
* The receiving view processes post data to mark lines received, update
  inventory and create ledger entries.  A "receive all" button expedites
  full receipt.  Partial receipts update quantities without closing a line.
* Detail view allows manual closing of an order (bypassing inventory changes)
  and shows received/remaining totals.
* **ProcurementDashboardView** exposes simple metrics: total orders, lines
  received/pending, and supplier count, shown as cards with links.

## API Endpoints

* `SupplierProductIDsView` (JSON) – used by front‑end forms to restrict line
  product choices when a supplier is selected.
* **NotifySupplierProductView** – CSRF-exempt POST endpoint at
  `/procurement/api/notify/supplier-product/` for remote paired instances to
  notify cost updates.  Validates a Bearer token against
  `PairedInstance.our_key`, expects JSON with `product_name` and `cost`, and
  updates the corresponding `SupplierProduct.cost`.

## Services

* `supplier_cost_totals()` – returns a dict of supplier ID → total cost across
  all their products.
* `best_supplier_products()` – picks the cheapest `SupplierProduct` per
  product ID, breaking ties by supplier total cost.
* `pending_po_by_product()` – returns a dict of product ID → remaining
  quantity on open purchase orders.

## Notes

* All forms and listings require authentication.
* Business logic in views is deliberately kept shallow; heavy lifting occurs in
  model save methods and ledger utilities.
* The receiving logic is written imperatively due to the need to update
  inventory and ledgers atomically while handling partial quantities.
* Supplier creation supports pre-filling from GET parameters and automatic
  linking to a `PairedInstance` for multi-site workflows.

---
