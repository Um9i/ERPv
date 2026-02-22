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

Indexes on product and customer fields assist with searching and reporting.

## Key Views & Processes

* CRUD for customers, contacts and customer products.  Lists support search
  and pagination; detail pages include paginated related orders/products.
* **CustomerProductIDsView** returns JSON of IDs for dynamic form filtering.
* Sales order creation works like purchase orders: inline formset, optional
  prefilled customer, product dropdown filtered by allowed products.
* Order and ship lists provide search by customer name or ID and pagination.
* Detail views show order lines and allow administrative closing.
* **SalesOrderShipView** handles shipments:
  * Validates inventory availability before decrementing stock and adding
    negative ledger entries.
  * Supports partial shipping and a "ship all" convenience.
  * Errors due to insufficient stock are collected and displayed on the form.
* The ship view updates the order timestamp and calculates remaining/total
  quantities.
* **SalesDashboardView** presents metrics: totals, shipped vs pending lines,
  and customer count.

## Workflows

1. Create customer and define what products they may buy along with prices.
2. Create sales order (single or multiple lines); submit to enter order.
3. Use ship interface to allocate stock; inventory and ledgers are updated.
4. Close orders either automatically when lines are fully shipped or manually
   via detail page.

All interactions are gated behind authentication; unauthorized requests are
redirected to login.

---
