"""Admin interface tests — filters, search, list views, inline editing, CSV export."""

import csv
import io
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client

from inventory.models import (
    Inventory,
    InventoryLedger,
    Location,
    Product,
    ProductionAllocated,
)
from procurement.models import (
    PurchaseLedger,
    PurchaseOrder,
    Supplier,
    SupplierContact,
    SupplierProduct,
)
from production.models import BillOfMaterials, BOMItem, Production
from sales.models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesLedger,
    SalesOrder,
)

pytestmark = pytest.mark.urls("main.test_urls")


def _product_with_deps(name, quantity=0, sale_price=None):
    p = Product.objects.bulk_create([Product(name=name, sale_price=sale_price)])[0]
    Inventory.objects.bulk_create([Inventory(product=p, quantity=quantity)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


@pytest.fixture
def admin_client(db):
    user = User.objects.create_superuser(
        username="admin", password="admin123", email="admin@test.com"
    )
    client = Client()
    client.force_login(user)
    return client


# ──────────────────────────────────────────────────────────────────────────────
# Inventory admin
# ──────────────────────────────────────────────────────────────────────────────


class TestProductAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        _product_with_deps("admin_prod_1")
        response = admin_client.get("/admin/inventory/product/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_changelist_search(self, admin_client):
        _product_with_deps("Searchable Widget")
        _product_with_deps("Other Thing")
        response = admin_client.get("/admin/inventory/product/?q=Searchable")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Searchable Widget" in body

    @pytest.mark.django_db
    def test_changelist_filter_catalogue(self, admin_client):
        _product_with_deps("cat_prod", sale_price=Decimal("10.00"))
        Product.objects.filter(name="cat_prod").update(catalogue_item=True)
        _product_with_deps("non_cat_prod")

        response = admin_client.get("/admin/inventory/product/?catalogue_item__exact=1")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_change_view_loads(self, admin_client):
        product = _product_with_deps("change_prod")
        response = admin_client.get(f"/admin/inventory/product/{product.pk}/change/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_delete_action_removed(self, admin_client):
        """delete_selected action should be removed from Product admin."""
        response = admin_client.get("/admin/inventory/product/")
        assert b"delete_selected" not in response.content


class TestInventoryLedgerAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        product = _product_with_deps("ledger_prod")
        InventoryLedger.objects.create(
            product=product, quantity=5, action="ADD", transaction_id=1
        )
        response = admin_client.get("/admin/inventory/inventoryledger/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_search_by_product_name(self, admin_client):
        product = _product_with_deps("UniqueSearchLedger")
        InventoryLedger.objects.create(
            product=product, quantity=1, action="ADD", transaction_id=1
        )
        response = admin_client.get(
            "/admin/inventory/inventoryledger/?q=UniqueSearchLedger"
        )
        assert response.status_code == 200
        assert b"UniqueSearchLedger" in response.content

    @pytest.mark.django_db
    def test_csv_export_action(self, admin_client):
        product = _product_with_deps("csv_ledger_prod")
        entry = InventoryLedger.objects.create(
            product=product, quantity=10, action="ADD", transaction_id=99
        )
        response = admin_client.post(
            "/admin/inventory/inventoryledger/",
            {"action": "export_as_csv", "_selected_action": [entry.pk]},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        content = response.content.decode()
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 row

    @pytest.mark.django_db
    def test_filter_by_action(self, admin_client):
        product = _product_with_deps("filter_prod")
        InventoryLedger.objects.create(
            product=product, quantity=1, action="ADD", transaction_id=1
        )
        response = admin_client.get("/admin/inventory/inventoryledger/?action=ADD")
        assert response.status_code == 200


class TestLocationAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        Location.objects.create(name="Warehouse A")
        response = admin_client.get("/admin/inventory/location/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_search(self, admin_client):
        Location.objects.create(name="UniqueWarehouse")
        response = admin_client.get("/admin/inventory/location/?q=UniqueWarehouse")
        assert response.status_code == 200
        assert b"UniqueWarehouse" in response.content


class TestStockTransferAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        response = admin_client.get("/admin/inventory/stocktransfer/")
        assert response.status_code == 200


class TestInventoryLocationAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        response = admin_client.get("/admin/inventory/inventorylocation/")
        assert response.status_code == 200


class TestInventoryAdjustAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        response = admin_client.get("/admin/inventory/inventoryadjust/")
        assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# Procurement admin
# ──────────────────────────────────────────────────────────────────────────────


class TestSupplierAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        Supplier.objects.create(name="Admin Supplier")
        response = admin_client.get("/admin/procurement/supplier/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_search(self, admin_client):
        Supplier.objects.create(name="UniqueSupplier123")
        response = admin_client.get("/admin/procurement/supplier/?q=UniqueSupplier123")
        assert response.status_code == 200
        assert b"UniqueSupplier123" in response.content

    @pytest.mark.django_db
    def test_change_view_with_inlines(self, admin_client):
        supplier = Supplier.objects.create(name="Inline Supplier")
        SupplierContact.objects.create(supplier=supplier, name="Contact 1")
        product = _product_with_deps("sup_inline_prod")
        SupplierProduct.objects.create(
            supplier=supplier, product=product, cost=Decimal("15.00")
        )
        response = admin_client.get(
            f"/admin/procurement/supplier/{supplier.pk}/change/"
        )
        assert response.status_code == 200


class TestPurchaseOrderAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        supplier = Supplier.objects.create(name="PO_Supplier")
        PurchaseOrder.objects.create(supplier=supplier)
        response = admin_client.get("/admin/procurement/purchaseorder/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_filter_by_supplier(self, admin_client):
        supplier = Supplier.objects.create(name="PO_Filter_Sup")
        PurchaseOrder.objects.create(supplier=supplier)
        response = admin_client.get(
            f"/admin/procurement/purchaseorder/?supplier__id__exact={supplier.pk}"
        )
        assert response.status_code == 200


class TestPurchaseLedgerAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        product = _product_with_deps("pl_admin_prod")
        supplier = Supplier.objects.create(name="pl_admin_sup")
        PurchaseLedger.objects.create(
            product=product,
            supplier=supplier,
            quantity=1,
            value=Decimal("50.00"),
            transaction_id=1,
        )
        response = admin_client.get("/admin/procurement/purchaseledger/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_csv_export_action(self, admin_client):
        product = _product_with_deps("pl_csv_prod")
        supplier = Supplier.objects.create(name="pl_csv_sup")
        entry = PurchaseLedger.objects.create(
            product=product,
            supplier=supplier,
            quantity=3,
            value=Decimal("90.00"),
            transaction_id=5,
        )
        response = admin_client.post(
            "/admin/procurement/purchaseledger/",
            {"action": "export_as_csv", "_selected_action": [entry.pk]},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    @pytest.mark.django_db
    def test_delete_action_removed(self, admin_client):
        response = admin_client.get("/admin/procurement/purchaseledger/")
        assert b"delete_selected" not in response.content


# ──────────────────────────────────────────────────────────────────────────────
# Sales admin
# ──────────────────────────────────────────────────────────────────────────────


class TestCustomerAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        Customer.objects.create(name="Admin Customer")
        response = admin_client.get("/admin/sales/customer/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_search(self, admin_client):
        Customer.objects.create(name="UniqueCust999")
        response = admin_client.get("/admin/sales/customer/?q=UniqueCust999")
        assert response.status_code == 200
        assert b"UniqueCust999" in response.content

    @pytest.mark.django_db
    def test_change_view_with_inlines(self, admin_client):
        customer = Customer.objects.create(name="Inline Customer")
        CustomerContact.objects.create(customer=customer, name="Contact A")
        product = _product_with_deps("cust_inline_prod")
        CustomerProduct.objects.create(
            customer=customer, product=product, price=Decimal("25.00")
        )
        response = admin_client.get(f"/admin/sales/customer/{customer.pk}/change/")
        assert response.status_code == 200


class TestSalesOrderAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        customer = Customer.objects.create(name="SO_Customer")
        SalesOrder.objects.create(customer=customer)
        response = admin_client.get("/admin/sales/salesorder/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_filter_by_customer(self, admin_client):
        customer = Customer.objects.create(name="SO_Filter_Cust")
        SalesOrder.objects.create(customer=customer)
        response = admin_client.get(
            f"/admin/sales/salesorder/?customer__id__exact={customer.pk}"
        )
        assert response.status_code == 200


class TestSalesLedgerAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        product = _product_with_deps("sl_admin_prod")
        customer = Customer.objects.create(name="sl_admin_cust")
        SalesLedger.objects.create(
            product=product,
            customer=customer,
            quantity=1,
            value=Decimal("100.00"),
            transaction_id=1,
        )
        response = admin_client.get("/admin/sales/salesledger/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_csv_export_action(self, admin_client):
        product = _product_with_deps("sl_csv_prod")
        customer = Customer.objects.create(name="sl_csv_cust")
        entry = SalesLedger.objects.create(
            product=product,
            customer=customer,
            quantity=2,
            value=Decimal("60.00"),
            transaction_id=10,
        )
        response = admin_client.post(
            "/admin/sales/salesledger/",
            {"action": "export_as_csv", "_selected_action": [entry.pk]},
        )
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    @pytest.mark.django_db
    def test_delete_action_removed(self, admin_client):
        response = admin_client.get("/admin/sales/salesledger/")
        assert b"delete_selected" not in response.content


# ──────────────────────────────────────────────────────────────────────────────
# Production admin
# ──────────────────────────────────────────────────────────────────────────────


class TestBillOfMaterialsAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        product = _product_with_deps("bom_admin_prod")
        BillOfMaterials.objects.create(product=product)
        response = admin_client.get("/admin/production/billofmaterials/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_change_view_with_inline_items(self, admin_client):
        product = _product_with_deps("bom_change_prod")
        comp = _product_with_deps("bom_comp")
        bom = BillOfMaterials.objects.create(product=product)
        BOMItem.objects.create(bom=bom, product=comp, quantity=5)
        response = admin_client.get(
            f"/admin/production/billofmaterials/{bom.pk}/change/"
        )
        assert response.status_code == 200


class TestProductionAdmin:
    @pytest.mark.django_db
    def test_changelist_loads(self, admin_client):
        product = _product_with_deps("prod_admin_prod")
        Production.objects.create(product=product, quantity=10)
        response = admin_client.get("/admin/production/production/")
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_filter_by_complete(self, admin_client):
        product = _product_with_deps("prod_filter_prod")
        Production.objects.create(product=product, quantity=5)
        response = admin_client.get("/admin/production/production/?complete__exact=0")
        assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# Config admin
# ──────────────────────────────────────────────────────────────────────────────


class TestCompanyConfigAdmin:
    @pytest.mark.django_db
    def test_changelist_redirects_to_singleton(self, admin_client):
        from config.models import CompanyConfig

        CompanyConfig.objects.create(pk=1, name="Test Co")
        response = admin_client.get("/admin/config/companyconfig/")
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_no_delete_permission(self, admin_client):
        from config.models import CompanyConfig

        instance = CompanyConfig.objects.create(pk=1, name="Test Co")
        response = admin_client.get(
            f"/admin/config/companyconfig/{instance.pk}/change/"
        )
        assert response.status_code == 200
        assert b"deletelink" not in response.content

    @pytest.mark.django_db
    def test_add_blocked_when_exists(self, admin_client):
        from config.models import CompanyConfig

        CompanyConfig.objects.create(pk=1, name="Test Co")
        response = admin_client.get("/admin/config/companyconfig/add/")
        assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# Hidden model permissions
# ──────────────────────────────────────────────────────────────────────────────


class TestHiddenModels:
    @pytest.mark.django_db
    def test_supplier_product_hidden_from_index(self, admin_client):
        """SupplierProduct should not appear on the admin index."""
        response = admin_client.get("/admin/")
        # The admin index should not have a link to SupplierProduct list
        assert b"/admin/procurement/supplierproduct/" not in response.content

    @pytest.mark.django_db
    def test_customer_product_hidden_from_index(self, admin_client):
        """CustomerProduct should not appear on the admin index."""
        response = admin_client.get("/admin/")
        assert b"/admin/sales/customerproduct/" not in response.content
