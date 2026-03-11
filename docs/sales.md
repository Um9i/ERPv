# Sales App

Handles customers, customer‑product pricing, sales orders, shipping, and
dashboards.

## Model Summary

* **Customer** with contact info; related to `SalesOrder` and
  `CustomerProduct`.
* **CustomerContact** for individuals at each customer.
* **CustomerProduct** links a `Customer` with a catalogue `Product` and a
  price.  Used to limit order lines to items sold to that customer.
* **SalesOrder** and **SalesOrderLine** mirror the procurement models but for
  outgoing goods.  Lines track quantity, shipped amount, completion, and
  monetized value once shipped.  Saving a line updates inventory and creates
  a `SalesLedger` entry.
* **SalesLedger** records shipments for audit/reporting, with positive
  quantities representing items shipped to customers.
* **PickList** – generated from a `SalesOrder` to guide warehouse staff
  through the picking process.  The `generate_for_order()` class method
  creates a pick list with location-aware bin breakdown, allocating stock
  from assigned inventory locations first and falling back to unallocated
  stock.  Lines with insufficient inventory are flagged as shortages.
* **PickListLine** – individual picking instruction referencing a sales order
  line, an optional `Location`, and an `is_shortage` flag.  Also tracks
  `confirmed` (boolean) and `confirmed_at` (timestamp) for the scan-to-pick
  confirmation workflow.

Indexes on product and customer fields assist with searching and reporting.

## Key Views & Processes

* CRUD for customers, contacts and customer products.  All forms use
  crispy‑forms with the `bootstrap5` pack for consistent Bootstrap styling.
  Lists support search and pagination; detail pages include analytics
  (total orders, open orders, total revenue, top products by value) alongside
  paginated related orders, products and contacts.
* **CustomerProductIDsView** returns JSON of IDs for dynamic form filtering.
* Sales order creation works like purchase orders: inline formset, optional
  prefilled customer, product dropdown filtered by allowed products.  A pick
  list is auto-generated on creation.
* Order and ship lists provide search by customer name or ID and pagination.
  The order list defaults to showing open orders (`?status=open`).
* The order list annotates each order with a `stock_ok` flag using bulk
  inventory queries, highlighting orders where stock is insufficient for
  remaining demand.
* Detail views show order lines and allow administrative closing.
* **SalesOrderShipView** handles shipments:
  * Pre-loads inventory in context for stock availability display.
  * Wraps shipment processing in `transaction.atomic()` with
    `select_for_update()` for race-condition safety.
  * Validates stock exists before decrementing.
  * Deducts from allocated stock locations first (ordered by name),
    then falls back to unallocated stock.
  * Creates inventory and sales ledger entries with location tags.
  * Supports partial shipping and a "ship all" convenience.
  * Errors due to insufficient stock are collected and displayed on the form.
* The ship view updates the order timestamp and calculates remaining/total
  quantities.
* **SalesOrderInvoiceView** renders a professional PDF invoice for any sales
  order using WeasyPrint.  The PDF is returned inline in the browser with
  filename `invoice-{order_number}.pdf`.
* **PickListCreateView** generates a new pick list for an order and redirects
  to the pick list detail page.
* **PickListDetailView** displays the picking guide with lines, locations,
  and shortage flags.  Includes a "Scan & Confirm" button linking to the
  confirmation workflow.
* **PickConfirmView** provides a scan-to-pick confirmation workflow:
  * GET renders a scanner UI with manual and camera-based barcode/QR input.
  * POST accepts `scan_value` (barcode or SKU lookup) or `line_id` (manual
    confirm) via AJAX, returning JSON responses.
  * Confirms the first unconfirmed line matching the scanned product.
  * Tracks confirmation progress with a live counter badge.
  * When all non-shortage lines are confirmed, offers a "Proceed to Ship"
    button.
* **PickConfirmResetView** resets all confirmations on a pick list.
* **ProductQRCodeView** generates a QR code PNG for a product's barcode,
  SKU, or name using `python-qrcode`.
* **SalesDashboardView** presents metrics: totals, shipped vs pending lines,
  customer count, fulfilment rate, and due-date awareness (orders due today
  or earlier).

## Workflows

1. Create customer and define what products they may buy along with prices.
2. Create sales order (single or multiple lines); submit to enter order.
   A pick list is generated automatically.
3. Use the pick confirmation workflow to scan-to-pick: scan barcodes/QR
   codes or manually confirm each line.  Progress is tracked in real time.
4. Use ship interface to allocate stock; inventory and ledgers are updated
   with location-level traceability.
4. Close orders either automatically when lines are fully shipped or manually
   via detail page.
5. Generate a PDF invoice from the order detail page at any time.

All interactions are gated behind authentication; unauthorized requests are
redirected to login.

* Customer creation supports pre-filling from GET parameters and automatic
  linking to a `PairedInstance` for multi-site workflows.

---
