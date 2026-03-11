from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from finance.models import FinanceDashboardSnapshot
from finance.services import refresh_finance_dashboard_cache
from main.factories import CustomerFactory, ProductFactory, SupplierFactory
from procurement.models import PurchaseLedger
from sales.models import SalesLedger


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
    user = User.objects.create_user(username="plcount")
    client.force_login(user)
    for i in range(5):
        p = ProductFactory()
        c = CustomerFactory()
        SalesLedger.objects.create(
            product=p,
            customer=c,
            quantity=1,
            value=Decimal("10.00"),
            transaction_id=100 + i,
        )

    # Warm caches
    client.get("/finance/reports/product-pl/")

    with CaptureQueriesContext(connection) as ctx:
        response = client.get("/finance/reports/product-pl/")
    assert response.status_code == 200
    # P&L uses ~22 queries (session/auth + aggregates + template).
    # Should not scale with product count.
    assert len(ctx) <= 30, f"Product P&L ran {len(ctx)} queries (expected ≤30)"
