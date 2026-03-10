from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

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
    # Dashboard uses ~43 queries (session/auth + aggregates + chart + stock
    # value + recent activity). Allow a buffer but catch N+1 regressions.
    assert len(ctx) <= 50, f"Finance dashboard ran {len(ctx)} queries (expected ≤50)"


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
