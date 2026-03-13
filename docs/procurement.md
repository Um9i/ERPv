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
* **Store Confirmation (Scan-to-Store)** – a barcode/QR scanning workflow for
  warehouse staff receiving goods from a purchase order into the store.
  `StoreConfirmView` presents a scanner UI (manual input + camera via the
  `BarcodeDetector` API) and confirms lines via AJAX.  Lines are matched by
  product barcode or SKU.  `StoreConfirmResetView` resets all confirmations.
  `PurchaseOrderLine` tracks `store_confirmed` and `store_confirmed_at`;
  `PurchaseOrder.all_store_confirmed` indicates when every line has been
  scanned in.  The PO detail page links directly to the scan-to-store page.
* Detail view allows manual closing of an order (bypassing inventory changes)
  and shows received/remaining totals.
* **ProcurementDashboardView** exposes simple metrics: total orders, lines
  received/pending, and supplier count, shown as cards with links.

### Reusable PO Templates

* **PurchaseOrderTemplate** and **PurchaseOrderTemplateLine** models allow
  users to save an existing PO as a named template.
* From the PO detail page, the "Save as Template" button opens a modal to
  name and store the template (supplier + lines).
* The template list page (`/procurement/po-templates/`) shows all saved
  templates with a "Create PO" button that redirects to the PO create form
  pre-populated with the template's supplier and line items.
* Templates can be deleted from the list page.

### Automated Receipt Matching

* The PO receiving page (`/procurement/purchase-orders/<id>/receive/`)
  includes a "Scan to Receive" barcode/SKU scanner.
* Scanning a product barcode or SKU automatically increments the receive
  quantity for the matching PO line, client-side.
* The user still submits the form to finalize the receipt.

### Bulk Close

* The PO list page supports multi-select checkboxes and a "Close Selected"
  bulk action to close multiple open orders at once.

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
