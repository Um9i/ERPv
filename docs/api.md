# API Documentation

ERPv exposes a set of **machine-to-machine (M2M) API endpoints** for multi-site pairing — allowing paired ERPv instances to exchange company info, catalogue data, customer/supplier notifications, and purchase orders.

## Interactive Docs

When the server is running, visit **`/api/docs/`** for the interactive Swagger UI, or **`/api/schema/`** to download the raw OpenAPI 3.0 schema.

## Authentication

All M2M endpoints require a **Bearer token** in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are generated automatically when a `PairedInstance` is created in **Config → Company & Integrations**. The token is the `our_key` field on the `PairedInstance` model.

Tokens are validated using constant-time comparison (`hmac.compare_digest`) to prevent timing attacks.

## Rate Limiting

All endpoints are rate-limited per IP address:

| Endpoint | Limit |
|----------|-------|
| `GET /config/api/company/` | 60 req/min |
| `GET /inventory/api/catalogue/` | 60 req/min |
| `POST /config/api/notify/customer/` | 30 req/min |
| `POST /config/api/notify/customer-product/` | 30 req/min |
| `POST /procurement/api/notify/supplier-product/` | 30 req/min |
| `POST /sales/api/notify/purchase-order/` | 30 req/min |

Exceeding the rate limit returns HTTP 429.

## Endpoints

### GET `/config/api/company/`

Returns company configuration (name, address, contact details, VAT/company numbers) for the local instance.

**Response:**
```json
{
  "name": "Acme Ltd",
  "address_line_1": "123 Industrial Park",
  "address_line_2": "",
  "city": "Manchester",
  "state": "",
  "postal_code": "M1 1AA",
  "country": "GB",
  "phone": "+44 161 000 0000",
  "email": "info@acme.example",
  "website": "https://acme.example",
  "vat_number": "GB123456789",
  "company_number": "12345678"
}
```

### GET `/inventory/api/catalogue/`

Returns all products marked as catalogue items with a sale price.

**Response:**
```json
[
  {
    "name": "Widget A",
    "description": "Standard widget",
    "sale_price": "29.99",
    "sku": null
  }
]
```

### POST `/config/api/notify/customer/`

Creates or links a Customer record from a remote paired instance.

**Request:**
```json
{
  "name": "Remote Co",
  "address_line_1": "456 High Street",
  "city": "London",
  "country": "GB"
}
```

**Response:**
```json
{"status": "ok", "created": true}
```

### POST `/config/api/notify/customer-product/`

Creates or updates a CustomerProduct with pricing from a remote instance.

**Request:**
```json
{
  "product_name": "Widget A",
  "price": "29.99"
}
```

**Response:**
```json
{"status": "ok", "created": true}
```

### POST `/procurement/api/notify/supplier-product/`

Updates the cost of a SupplierProduct from a remote paired supplier. Triggers a notification to all local users if the cost changed.

**Request:**
```json
{
  "product_name": "Raw Material X",
  "cost": "12.50"
}
```

**Response:**
```json
{"status": "ok"}
```

### POST `/sales/api/notify/purchase-order/`

Receives a purchase order from a remote paired customer and auto-creates a matching SalesOrder with line items. Products that can't be resolved are skipped gracefully.

**Request:**
```json
{
  "order_number": "PO-0042",
  "due_date": "2026-04-15",
  "lines": [
    {"product_name": "Widget A", "quantity": 10},
    {"product_name": "Widget B", "quantity": 5}
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "sales_order": "SO-0001",
  "skipped_products": []
}
```

## Infrastructure Endpoints

### GET `/healthz/`

Unauthenticated health check for container orchestration probes.

**Response (healthy):** `200 OK`
```json
{"status": "ok", "checks": {"database": "ok"}}
```

**Response (unhealthy):** `503 Service Unavailable`
```json
{"status": "error", "checks": {"database": "error"}}
```
