import csv
import io
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from finance.models import FinanceDashboardSnapshot
from finance.services import _compute_stock_value, refresh_finance_dashboard_cache
from inventory.models import Inventory, Product, ProductionAllocated
from main.factories import CustomerFactory, ProductFactory, SupplierFactory
from procurement.models import (
    PurchaseLedger,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierProduct,
)
from production.models import BillOfMaterials, BOMItem
from sales.models import (
    Customer,
    CustomerProduct,
    SalesLedger,
    SalesOrder,
    SalesOrderLine,
)


@pytest.fixture
def staff_client(client, db):
    user = User.objects.create_user(username="staff")
    client.force_login(user)
    return client


def _product_with_deps(name, quantity=0, sale_price=None):
    """Create a Product + Inventory + ProductionAllocated in bulk."""
    p = Product.objects.bulk_create([Product(name=name, sale_price=sale_price)])[0]
    Inventory.objects.bulk_create([Inventory(product=p, quantity=quantity)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Existing tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_finance_dashboard_shows_totals(client):
    user = User.objects.create_user(username="finance")
    client.force_login(user)
    product = ProductFactory()
    customer = CustomerFactory()
    supplier = SupplierFactory()

    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=2,
        value=Decimal("50.00"),
        transaction_id=1,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=1,
        value=Decimal("20.00"),
        transaction_id=2,
    )

    response = client.get("/finance/")
    assert response.status_code == 200
    assert response.context["sales_total"] == Decimal("50.00")
    assert response.context["purchase_total"] == Decimal("20.00")


@pytest.mark.django_db
def test_sales_ledger_archive_lists_entry(client):
    user = User.objects.create_user(username="archive")
    client.force_login(user)
    product = ProductFactory()
    customer = CustomerFactory()
    entry = SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=1,
        value=Decimal("10.00"),
        transaction_id=99,
    )

    response = client.get("/finance/sales/")
    assert response.status_code == 200
    body = response.content.decode()
    assert entry.product.name in body
    assert customer.name in body


@pytest.mark.django_db
def test_finance_dashboard_query_count(client):
    """Guard against N+1 regressions on the finance dashboard."""
    user = User.objects.create_user(username="qcount")
    client.force_login(user)
    product = ProductFactory()
    customer = CustomerFactory()
    supplier = SupplierFactory()
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=1,
        value=Decimal("10.00"),
        transaction_id=1,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=1,
        value=Decimal("5.00"),
        transaction_id=2,
    )

    # Warm any first-request caches
    client.get("/finance/")

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/finance/")
    assert response.status_code == 200
    # With the materialized cache the dashboard needs far fewer queries
    # (session/auth + snapshot read + recent activity).
    assert len(ctx) <= 30, f"Finance dashboard ran {len(ctx)} queries (expected ≤30)"


@pytest.mark.django_db
def test_finance_cache_refresh_computes_totals():
    """refresh_finance_dashboard_cache populates the singleton snapshot."""
    product = ProductFactory()
    customer = CustomerFactory()
    supplier = SupplierFactory()

    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=3,
        value=Decimal("75.00"),
        transaction_id=1,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=2,
        value=Decimal("30.00"),
        transaction_id=2,
    )

    snapshot = refresh_finance_dashboard_cache()
    assert snapshot.sales_total == Decimal("75.00")
    assert snapshot.purchase_total == Decimal("30.00")
    assert snapshot.month_sales_total == Decimal("75.00")
    assert snapshot.month_purchase_total == Decimal("30.00")
    assert snapshot.updated_at is not None


@pytest.mark.django_db
def test_finance_cache_signal_updates_on_ledger_write():
    """Creating a SalesLedger row triggers a cache refresh via signal."""
    product = ProductFactory()
    customer = CustomerFactory()

    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=1,
        value=Decimal("100.00"),
        transaction_id=10,
    )

    snapshot = FinanceDashboardSnapshot.load()
    assert snapshot.sales_total == Decimal("100.00")


@pytest.mark.django_db
def test_finance_cache_chart_data_has_12_months():
    """Chart data in the snapshot always contains 12 months."""
    snapshot = refresh_finance_dashboard_cache()
    chart = snapshot.chart_data
    assert len(chart["months"]) == 12
    assert len(chart["sales"]) == 12
    assert len(chart["purchases"]) == 12


@pytest.mark.django_db
def test_finance_dashboard_uses_cached_values(client):
    """Dashboard view reads from the snapshot rather than computing live."""
    user = User.objects.create_user(username="cached")
    client.force_login(user)
    product = ProductFactory()
    customer = CustomerFactory()
    supplier = SupplierFactory()

    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=1,
        value=Decimal("200.00"),
        transaction_id=20,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=1,
        value=Decimal("80.00"),
        transaction_id=21,
    )

    response = client.get("/finance/")
    assert response.status_code == 200
    assert response.context["sales_total"] == Decimal("200.00")
    assert response.context["purchase_total"] == Decimal("80.00")
    assert response.context["gross_profit"] == Decimal("120.00")


@pytest.mark.django_db
def test_product_pl_query_count(client):
    """Guard against N+1 regressions on the Product P&L report."""
    from inventory.models import Inventory, ProductionAllocated
    from sales.models import Customer

    user = User.objects.create_user(username="plcount")
    client.force_login(user)
    products = Product.objects.bulk_create(
        [Product(name=f"pl_prod_{i}") for i in range(5)]
    )
    Inventory.objects.bulk_create([Inventory(product=p) for p in products])
    ProductionAllocated.objects.bulk_create(
        [ProductionAllocated(product=p) for p in products]
    )
    customers = Customer.objects.bulk_create(
        [Customer(name=f"pl_cust_{i}") for i in range(5)]
    )
    SalesLedger.objects.bulk_create(
        [
            SalesLedger(
                product=products[i],
                customer=customers[i],
                quantity=1,
                value=Decimal("10.00"),
                transaction_id=100 + i,
            )
            for i in range(5)
        ]
    )

    # Warm caches
    client.get("/finance/reports/product-pl/")

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/finance/reports/product-pl/")
    assert response.status_code == 200
    # P&L uses ~22 queries (session/auth + aggregates + template).
    # Should not scale with product count.
    assert len(ctx) <= 30, f"Product P&L ran {len(ctx)} queries (expected ≤30)"


# ──────────────────────────────────────────────────────────────────────────────
# Margin & P&L calculations
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_product_pl_margin_calculation(staff_client):
    """Verify margin %, gross profit, and per-row totals for a single product."""
    product = _product_with_deps("margin_prod", sale_price=Decimal("100.00"))
    supplier = Supplier.objects.create(name="margin_supplier")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("60.00")
    )
    customer = Customer.objects.create(name="margin_customer")
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=10,
        value=Decimal("1000.00"),
        transaction_id=1,
    )

    response = staff_client.get("/finance/reports/product-pl/")
    assert response.status_code == 200

    rows = response.context["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["unit_cost"] == Decimal("60.00")
    assert row["total_revenue"] == Decimal("1000.00")
    assert row["total_cost"] == Decimal("600.00")  # 10 × 60
    assert row["gross_profit"] == Decimal("400.00")
    assert row["margin_pct"] == pytest.approx(40.0)


@pytest.mark.django_db
def test_product_pl_zero_revenue_margin(staff_client):
    """Products with zero revenue should have None margin_pct."""
    product = _product_with_deps("zero_rev_prod")
    customer = Customer.objects.create(name="zero_cust")
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=5,
        value=Decimal("0.00"),
        transaction_id=1,
    )

    response = staff_client.get("/finance/reports/product-pl/")
    rows = response.context["rows"]
    assert len(rows) == 1
    assert rows[0]["margin_pct"] is None


@pytest.mark.django_db
def test_product_pl_no_supplier_cost(staff_client):
    """Product with no supplier cost should show zero unit cost."""
    product = _product_with_deps("nocost_prod")
    customer = Customer.objects.create(name="nocost_cust")
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=3,
        value=Decimal("90.00"),
        transaction_id=1,
    )

    response = staff_client.get("/finance/reports/product-pl/")
    rows = response.context["rows"]
    assert len(rows) == 1
    assert rows[0]["unit_cost"] == Decimal("0")
    assert rows[0]["gross_profit"] == Decimal("90.00")


@pytest.mark.django_db
def test_product_pl_sorting_by_margin_pct(staff_client):
    """Sort=margin_pct orders rows by margin percentage descending."""
    supplier = Supplier.objects.create(name="sort_supplier")
    customer = Customer.objects.create(name="sort_cust")

    high_margin = _product_with_deps("high_margin", sale_price=Decimal("100.00"))
    SupplierProduct.objects.create(
        supplier=supplier, product=high_margin, cost=Decimal("10.00")
    )
    SalesLedger.objects.create(
        product=high_margin,
        customer=customer,
        quantity=1,
        value=Decimal("100.00"),
        transaction_id=1,
    )

    low_margin = _product_with_deps("low_margin", sale_price=Decimal("100.00"))
    SupplierProduct.objects.create(
        supplier=supplier, product=low_margin, cost=Decimal("90.00")
    )
    SalesLedger.objects.create(
        product=low_margin,
        customer=customer,
        quantity=1,
        value=Decimal("100.00"),
        transaction_id=2,
    )

    response = staff_client.get("/finance/reports/product-pl/?sort=margin_pct")
    rows = response.context["rows"]
    assert rows[0]["product"].name == "high_margin"
    assert rows[1]["product"].name == "low_margin"


@pytest.mark.django_db
def test_product_pl_sorting_by_revenue(staff_client):
    """Sort=revenue orders rows by total_revenue descending."""
    customer = Customer.objects.create(name="rev_cust")

    prod_a = _product_with_deps("rev_low")
    SalesLedger.objects.create(
        product=prod_a,
        customer=customer,
        quantity=1,
        value=Decimal("50.00"),
        transaction_id=1,
    )

    prod_b = _product_with_deps("rev_high")
    SalesLedger.objects.create(
        product=prod_b,
        customer=customer,
        quantity=1,
        value=Decimal("200.00"),
        transaction_id=2,
    )

    response = staff_client.get("/finance/reports/product-pl/?sort=revenue")
    rows = response.context["rows"]
    assert rows[0]["product"].name == "rev_high"


@pytest.mark.django_db
def test_product_pl_empty_no_sales(staff_client):
    """P&L report with no sales data returns empty rows."""
    response = staff_client.get("/finance/reports/product-pl/")
    assert response.status_code == 200
    assert response.context["rows"] == []
    assert response.context["total_revenue"] == Decimal("0")
    assert response.context["total_profit"] == Decimal("0")
    assert response.context["avg_margin_pct"] is None


@pytest.mark.django_db
def test_product_pl_aggregate_totals(staff_client):
    """Verify total_revenue, total_cost, total_profit context sums."""
    supplier = Supplier.objects.create(name="agg_supplier")
    customer = Customer.objects.create(name="agg_cust")

    p1 = _product_with_deps("agg1")
    SupplierProduct.objects.create(supplier=supplier, product=p1, cost=Decimal("20.00"))
    SalesLedger.objects.create(
        product=p1,
        customer=customer,
        quantity=5,
        value=Decimal("250.00"),
        transaction_id=1,
    )

    p2 = _product_with_deps("agg2")
    SupplierProduct.objects.create(supplier=supplier, product=p2, cost=Decimal("30.00"))
    SalesLedger.objects.create(
        product=p2,
        customer=customer,
        quantity=3,
        value=Decimal("150.00"),
        transaction_id=2,
    )

    response = staff_client.get("/finance/reports/product-pl/")
    ctx = response.context
    assert ctx["total_revenue"] == Decimal("400.00")
    assert ctx["total_cost"] == Decimal("190.00")  # 5×20 + 3×30
    assert ctx["total_profit"] == Decimal("210.00")


@pytest.mark.django_db
def test_product_pl_chart_data_top10(staff_client):
    """Chart data contains at most 10 products, sorted by gross profit."""
    customer = Customer.objects.create(name="chart_cust")
    for i in range(12):
        p = _product_with_deps(f"chart_prod_{i}")
        SalesLedger.objects.create(
            product=p,
            customer=customer,
            quantity=1,
            value=Decimal(str(10 + i)),
            transaction_id=i,
        )

    response = staff_client.get("/finance/reports/product-pl/")
    chart = response.context["chart_data"]
    assert len(chart["labels"]) <= 10
    assert len(chart["values"]) <= 10
    assert len(chart["colors"]) <= 10


@pytest.mark.django_db
def test_product_pl_chart_color_coding(staff_client):
    """Chart colors reflect margin thresholds: green>=30%, yellow>=10%, red<10%."""
    supplier = Supplier.objects.create(name="color_supplier")
    customer = Customer.objects.create(name="color_cust")

    # High margin (>30%)
    hi = _product_with_deps("hi_margin")
    SupplierProduct.objects.create(supplier=supplier, product=hi, cost=Decimal("10.00"))
    SalesLedger.objects.create(
        product=hi,
        customer=customer,
        quantity=10,
        value=Decimal("200.00"),
        transaction_id=1,
    )

    # Medium margin (~17%)
    mid = _product_with_deps("mid_margin")
    SupplierProduct.objects.create(
        supplier=supplier, product=mid, cost=Decimal("50.00")
    )
    SalesLedger.objects.create(
        product=mid,
        customer=customer,
        quantity=10,
        value=Decimal("600.00"),
        transaction_id=2,
    )

    # Low margin (~5%)
    lo = _product_with_deps("lo_margin")
    SupplierProduct.objects.create(supplier=supplier, product=lo, cost=Decimal("95.00"))
    SalesLedger.objects.create(
        product=lo,
        customer=customer,
        quantity=10,
        value=Decimal("1000.00"),
        transaction_id=3,
    )

    response = staff_client.get("/finance/reports/product-pl/")
    chart = response.context["chart_data"]
    colors = dict(zip(chart["labels"], chart["colors"]))
    assert colors["hi_margin"] == "#198754"  # green
    assert colors["mid_margin"] == "#ffc107"  # yellow
    assert colors["lo_margin"] == "#dc3545"  # red


# ──────────────────────────────────────────────────────────────────────────────
# Stock value computation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_stock_value_with_supplier_cost():
    """Stock value = sum(qty × cheapest supplier cost)."""
    product = _product_with_deps("sv_prod", quantity=50)
    supplier = Supplier.objects.create(name="sv_supplier")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("10.00")
    )

    value = _compute_stock_value()
    assert value == Decimal("500.00")


@pytest.mark.django_db
def test_stock_value_cheapest_supplier_wins():
    """Multiple suppliers — cheapest cost is used."""
    product = _product_with_deps("multi_sup_prod", quantity=20)
    s1 = Supplier.objects.create(name="expensive")
    s2 = Supplier.objects.create(name="cheap")
    SupplierProduct.objects.create(supplier=s1, product=product, cost=Decimal("50.00"))
    SupplierProduct.objects.create(supplier=s2, product=product, cost=Decimal("10.00"))

    value = _compute_stock_value()
    assert value == Decimal("200.00")  # 20 × 10


@pytest.mark.django_db
def test_stock_value_bom_fallback():
    """Products without supplier cost use BOM component costs instead."""
    parent = _product_with_deps("bom_parent", quantity=5)
    comp = _product_with_deps("bom_comp")
    supplier = Supplier.objects.create(name="comp_supplier")
    SupplierProduct.objects.create(
        supplier=supplier, product=comp, cost=Decimal("8.00")
    )

    bom = BillOfMaterials.objects.create(product=parent)
    BOMItem.objects.create(bom=bom, product=comp, quantity=3)

    value = _compute_stock_value()
    # parent: 5 × (3 × 8) = 120, comp: 0 qty
    assert value == Decimal("120.00")


@pytest.mark.django_db
def test_stock_value_no_cost_returns_zero():
    """Products with no supplier cost and no BOM contribute zero."""
    _product_with_deps("orphan_prod", quantity=100)
    value = _compute_stock_value()
    assert value == Decimal("0")


@pytest.mark.django_db
def test_stock_value_zero_quantity_ignored():
    """Products with zero inventory don't inflate stock value."""
    product = _product_with_deps("zero_qty_prod", quantity=0)
    supplier = Supplier.objects.create(name="zero_sup")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("100.00")
    )

    value = _compute_stock_value()
    assert value == Decimal("0")


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard cache refresh edge cases
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_cache_refresh_empty_ledgers():
    """Refresh with no ledger entries should produce all-zero snapshot."""
    snapshot = refresh_finance_dashboard_cache()
    assert snapshot.sales_total == Decimal("0")
    assert snapshot.purchase_total == Decimal("0")
    assert snapshot.month_sales_total == Decimal("0")
    assert snapshot.month_purchase_total == Decimal("0")
    assert snapshot.stock_value == Decimal("0")


@pytest.mark.django_db
def test_cache_refresh_stores_current_month():
    """Snapshot records the year/month for staleness detection."""
    snapshot = refresh_finance_dashboard_cache()
    now = timezone.now()
    assert snapshot.month_year == now.year
    assert snapshot.month_month == now.month


@pytest.mark.django_db
def test_dashboard_stale_cache_triggers_refresh(staff_client):
    """If snapshot month differs from current month, dashboard auto-refreshes."""
    product = ProductFactory()
    customer = CustomerFactory()
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=1,
        value=Decimal("50.00"),
        transaction_id=1,
    )
    # Create a snapshot in a different month
    snapshot = refresh_finance_dashboard_cache()
    snapshot.month_month = (timezone.now().month % 12) + 1  # force a different month
    snapshot.save()

    response = staff_client.get("/finance/")
    assert response.status_code == 200
    # Should have auto-refreshed to current month
    assert response.context["sales_total"] == Decimal("50.00")


@pytest.mark.django_db
def test_finance_dashboard_stock_value_in_context(staff_client):
    """Dashboard context includes stock_value from snapshot."""
    product = _product_with_deps("sv_ctx_prod", quantity=10)
    supplier = Supplier.objects.create(name="sv_ctx_sup")
    SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("25.00")
    )
    refresh_finance_dashboard_cache()

    response = staff_client.get("/finance/")
    assert response.status_code == 200
    assert response.context["stock_value"] == Decimal("250.00")


# ──────────────────────────────────────────────────────────────────────────────
# Purchase ledger views
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_purchase_ledger_archive_lists_entry(staff_client):
    """Purchase ledger archive view lists entries."""
    product = ProductFactory()
    supplier = SupplierFactory()
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=5,
        value=Decimal("200.00"),
        transaction_id=1,
    )

    response = staff_client.get("/finance/purchases/")
    assert response.status_code == 200
    body = response.content.decode()
    assert product.name in body
    assert supplier.name in body


@pytest.mark.django_db
def test_purchase_ledger_archive_overall_total(staff_client):
    """Overall total aggregates all purchase ledger entries."""
    product = ProductFactory()
    supplier = SupplierFactory()
    for i in range(3):
        PurchaseLedger.objects.create(
            product=product,
            supplier=supplier,
            quantity=1,
            value=Decimal("100.00"),
            transaction_id=i,
        )

    response = staff_client.get("/finance/purchases/")
    assert response.context["overall_total"] == Decimal("300.00")


@pytest.mark.django_db
def test_purchase_ledger_filter_by_supplier(staff_client):
    """Filtering by supplier_id narrows results."""
    product = ProductFactory()
    s1 = Supplier.objects.create(name="PL_Supplier_A")
    s2 = Supplier.objects.create(name="PL_Supplier_B")
    PurchaseLedger.objects.create(
        product=product,
        supplier=s1,
        quantity=1,
        value=Decimal("50.00"),
        transaction_id=1,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=s2,
        quantity=1,
        value=Decimal("70.00"),
        transaction_id=2,
    )

    response = staff_client.get(f"/finance/purchases/?supplier={s1.pk}")
    assert response.context["overall_total"] == Decimal("50.00")


# ──────────────────────────────────────────────────────────────────────────────
# Sales ledger filter
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sales_ledger_filter_by_customer(staff_client):
    """Filtering sales ledger by customer_id narrows results."""
    product = ProductFactory()
    c1 = Customer.objects.create(name="SL_Cust_A")
    c2 = Customer.objects.create(name="SL_Cust_B")
    SalesLedger.objects.create(
        product=product,
        customer=c1,
        quantity=1,
        value=Decimal("100.00"),
        transaction_id=1,
    )
    SalesLedger.objects.create(
        product=product,
        customer=c2,
        quantity=1,
        value=Decimal("200.00"),
        transaction_id=2,
    )

    response = staff_client.get(f"/finance/sales/?customer={c1.pk}")
    assert response.context["overall_total"] == Decimal("100.00")


@pytest.mark.django_db
def test_sales_ledger_filter_by_product(staff_client):
    """Filtering sales ledger by product_id narrows results."""
    p1 = _product_with_deps("sl_prod_a")
    p2 = _product_with_deps("sl_prod_b")
    customer = Customer.objects.create(name="SL_Prod_Cust")
    SalesLedger.objects.create(
        product=p1,
        customer=customer,
        quantity=1,
        value=Decimal("80.00"),
        transaction_id=1,
    )
    SalesLedger.objects.create(
        product=p2,
        customer=customer,
        quantity=1,
        value=Decimal("120.00"),
        transaction_id=2,
    )

    response = staff_client.get(f"/finance/sales/?product={p1.pk}")
    assert response.context["overall_total"] == Decimal("80.00")


# ──────────────────────────────────────────────────────────────────────────────
# CSV export views
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_sales_ledger_csv_export(staff_client):
    """Sales CSV export returns correct headers and data rows."""
    product = ProductFactory()
    customer = CustomerFactory()
    SalesLedger.objects.create(
        product=product,
        customer=customer,
        quantity=3,
        value=Decimal("45.00"),
        transaction_id=7,
    )

    response = staff_client.get("/finance/sales/export/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"

    content = response.content.decode()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert rows[0] == [
        "Date",
        "Customer",
        "Product",
        "Quantity",
        "Value",
        "Transaction",
    ]
    assert len(rows) == 2
    assert rows[1][1] == customer.name
    assert rows[1][2] == product.name
    assert rows[1][3] == "3"
    assert rows[1][4] == "45.00"
    assert rows[1][5] == "SO00007"


@pytest.mark.django_db
def test_purchase_ledger_csv_export(staff_client):
    """Purchase CSV export returns correct headers and data rows."""
    product = ProductFactory()
    supplier = SupplierFactory()
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=10,
        value=Decimal("500.00"),
        transaction_id=42,
    )

    response = staff_client.get("/finance/purchases/export/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"

    content = response.content.decode()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert rows[0] == [
        "Date",
        "Supplier",
        "Product",
        "Quantity",
        "Value",
        "Transaction",
    ]
    assert len(rows) == 2
    assert rows[1][1] == supplier.name
    assert rows[1][5] == "PO00042"


@pytest.mark.django_db
def test_sales_csv_export_customer_filter(staff_client):
    """Sales CSV export filters by customer."""
    product = ProductFactory()
    c1 = Customer.objects.create(name="CSV_Cust_A")
    c2 = Customer.objects.create(name="CSV_Cust_B")
    SalesLedger.objects.create(
        product=product,
        customer=c1,
        quantity=1,
        value=Decimal("10.00"),
        transaction_id=1,
    )
    SalesLedger.objects.create(
        product=product,
        customer=c2,
        quantity=1,
        value=Decimal("20.00"),
        transaction_id=2,
    )

    response = staff_client.get(f"/finance/sales/export/?customer={c1.pk}")
    content = response.content.decode()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2  # header + 1 row
    assert rows[1][1] == "CSV_Cust_A"


@pytest.mark.django_db
def test_purchase_csv_export_supplier_filter(staff_client):
    """Purchase CSV export filters by supplier."""
    product = ProductFactory()
    s1 = Supplier.objects.create(name="CSV_Sup_A")
    s2 = Supplier.objects.create(name="CSV_Sup_B")
    PurchaseLedger.objects.create(
        product=product,
        supplier=s1,
        quantity=1,
        value=Decimal("30.00"),
        transaction_id=1,
    )
    PurchaseLedger.objects.create(
        product=product,
        supplier=s2,
        quantity=1,
        value=Decimal("40.00"),
        transaction_id=2,
    )

    response = staff_client.get(f"/finance/purchases/export/?supplier={s1.pk}")
    content = response.content.decode()
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[1][1] == "CSV_Sup_A"


# ──────────────────────────────────────────────────────────────────────────────
# Outstanding orders view
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_outstanding_orders_view_empty(staff_client):
    """Outstanding orders view with no open orders shows zero values."""
    response = staff_client.get("/finance/reports/outstanding/")
    assert response.status_code == 200
    assert response.context["open_sales_value"] == Decimal("0")
    assert response.context["open_purchases_value"] == Decimal("0")


@pytest.mark.django_db
def test_outstanding_orders_shows_open_sales(staff_client):
    """Outstanding orders includes sales orders with incomplete lines."""
    product = _product_with_deps("oo_prod", quantity=100, sale_price=Decimal("50.00"))
    product.price = Decimal("50.00")
    product.save()
    customer = Customer.objects.create(name="oo_cust")
    cp = CustomerProduct.objects.create(
        customer=customer, product=product, price=Decimal("50.00")
    )
    so = SalesOrder.objects.create(customer=customer)
    SalesOrderLine.objects.create(
        sales_order=so, product=cp, quantity=10, complete=False
    )

    response = staff_client.get("/finance/reports/outstanding/")
    assert response.status_code == 200
    assert response.context["open_sales_value"] > Decimal("0")


@pytest.mark.django_db
def test_outstanding_orders_shows_open_purchases(staff_client):
    """Outstanding orders includes purchase orders with incomplete lines."""
    product = _product_with_deps("oo_po_prod", quantity=0)
    product.cost = Decimal("25.00")
    product.save()
    supplier = Supplier.objects.create(name="oo_po_supplier")
    sp = SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=Decimal("25.00")
    )
    po = PurchaseOrder.objects.create(supplier=supplier)
    PurchaseOrderLine.objects.create(
        purchase_order=po, product=sp, quantity=20, complete=False
    )

    response = staff_client.get("/finance/reports/outstanding/")
    assert response.status_code == 200
    assert response.context["open_purchases_value"] > Decimal("0")
