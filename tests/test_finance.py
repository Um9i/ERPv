from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from finance import views
from procurement.models import PurchaseLedger
from sales.models import SalesLedger
from main.factories import ProductFactory, CustomerFactory, SupplierFactory


@pytest.mark.django_db
def test_finance_dashboard_shows_totals(client):
    user = User.objects.create_user(username="finance", password="pw")
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
    user = User.objects.create_user(username="archive", password="pw")
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
def test_supplier_billing_summary(client):
    user = User.objects.create_user(username="supplier", password="pw")
    client.force_login(user)
    product = ProductFactory()
    supplier = SupplierFactory()
    PurchaseLedger.objects.create(
        product=product,
        supplier=supplier,
        quantity=3,
        value=Decimal("30.00"),
        transaction_id=5,
    )

    now = timezone.now()
    response = client.get(f"/finance/supplier-bills/{now.year}/{now.month}/")
    assert response.status_code == 200
    rows = list(response.context["supplier_rows"])
    assert rows[0]["total_value"] == Decimal("30.00")


@pytest.mark.django_db
def test_customer_invoice_pdf_graceful_without_weasy(client, monkeypatch):
    user = User.objects.create_user(username="pdf", password="pw")
    client.force_login(user)
    # force PDF dependency absence to exercise fallback
    monkeypatch.setattr(views, "HTML", None)

    now = timezone.now()
    url = f"/finance/invoices/{now.year}/{now.month}/pdf/"
    response = client.get(url)
    assert response.status_code == 501
    assert "WeasyPrint" in response.content.decode()
