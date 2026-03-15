"""Tests for production model methods, properties, and validation."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from inventory.models import Inventory, Product
from procurement.models import Supplier, SupplierProduct
from production.models import BillOfMaterials, BOMItem, Production, ProductionLedger

pytestmark = pytest.mark.integration


@pytest.fixture
def component(db):
    return Product.objects.create(name="Component A", sale_price=Decimal("5.00"))


@pytest.fixture
def finished(db):
    return Product.objects.create(name="Finished Good", sale_price=Decimal("50.00"))


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(name="Parts Co")


@pytest.fixture
def supplier_product(supplier, component):
    return SupplierProduct.objects.create(
        supplier=supplier, product=component, cost=Decimal("3.00")
    )


@pytest.fixture
def bom_with_item(finished, component, supplier_product):
    """Create a BOM for the finished product with a single component."""
    bom = BillOfMaterials.objects.create(product=finished)
    BOMItem.objects.create(bom=bom, product=component, quantity=2)
    return bom


@pytest.fixture
def stocked_component(component):
    Inventory.objects.filter(product=component).update(quantity=100)
    return component


# ── BOMItem validation ───────────────────────────────────────────────
class TestBOMItemValidation:
    def test_self_reference_rejected(self, finished, supplier_product):
        bom = BillOfMaterials.objects.create(product=finished)
        item = BOMItem(bom=bom, product=finished, quantity=1)
        with pytest.raises(ValidationError, match="inceptions"):
            item.clean()

    def test_unsourceable_product_rejected(self, finished):
        """A BOM component with no supplier and no sub-BOM is rejected."""
        orphan = Product.objects.create(name="Orphan Part")
        bom = BillOfMaterials.objects.create(product=finished)
        item = BOMItem(bom=bom, product=orphan, quantity=1)
        with pytest.raises(ValidationError, match="no supplier"):
            item.clean()

    def test_circular_reference_detected(self, finished, component, supplier_product):
        """A → B → A circular BOM is caught."""
        bom_a = BillOfMaterials.objects.create(product=finished)
        BOMItem.objects.create(bom=bom_a, product=component, quantity=1)
        # B has its own BOM pointing back to A
        bom_b = BillOfMaterials.objects.create(product=component)
        item = BOMItem(bom=bom_b, product=finished, quantity=1)
        # finished needs a supplier to pass sourceable check
        SupplierProduct.objects.create(
            supplier=supplier_product.supplier,
            product=finished,
            cost=Decimal("10.00"),
        )
        with pytest.raises(ValidationError, match="Circular"):
            item.clean()


# ── Production properties ────────────────────────────────────────────
class TestProductionProperties:
    def test_str(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        assert str(job) == "Finished Good"

    def test_order_number(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=5)
        job.save()
        assert job.order_number.startswith("PR")

    def test_date_property(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=5)
        job.save()
        assert job.date == job.created_at

    def test_remaining(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        job.quantity_received = 3
        assert job.remaining == 7

    def test_status_lifecycle(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        assert job.status == "Allocated"

        # partially receive
        job.quantity_received = 2
        job.save()
        assert job.status == "Completing"

        # close
        job.closed = True
        assert job.status == "Closed"


# ── Production.materials_available ───────────────────────────────────
class TestProductionMaterials:
    def test_materials_available_true(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        # 10 qty × 2 per unit = 20 needed, 100 available
        assert job.materials_available is True

    def test_materials_available_false(self, bom_with_item, component):
        Inventory.objects.filter(product=component).update(quantity=0)
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        assert job.materials_available is False

    def test_materials_available_no_bom(self, db):
        p = Product.objects.create(name="No BOM Product")
        job = Production(product=p, quantity=5)
        # Can't save without BOM, test the property directly
        job.pk = None
        assert job.materials_available is False

    def test_max_receivable(self, bom_with_item, stocked_component):
        job = Production(product=bom_with_item.product, quantity=10)
        job.save()
        # 100 avail, 2 per unit, but capped at remaining (10)
        assert job.max_receivable == 10


# ── Production.clean ─────────────────────────────────────────────────
class TestProductionClean:
    def test_clean_no_bom_raises(self, db):
        p = Product.objects.create(name="NoBOM")
        job = Production(product=p, quantity=5)
        with pytest.raises(ValidationError, match="no Bill"):
            job.clean()


# ── Production.cancel ────────────────────────────────────────────────
class TestProductionCancel:
    def test_cancel_releases_materials(self, bom_with_item, stocked_component):
        job = Production.objects.create(product=bom_with_item.product, quantity=5)
        assert job.bom_allocated is True
        job.cancel()
        job.refresh_from_db()
        assert job.closed is True
        assert job.bom_allocated is False

    def test_cancel_idempotent(self, bom_with_item, stocked_component):
        job = Production.objects.create(product=bom_with_item.product, quantity=5)
        job.cancel()
        # second cancel does nothing
        job.cancel()
        job.refresh_from_db()
        assert job.closed is True


# ── ProductionLedger ─────────────────────────────────────────────────
class TestProductionLedger:
    def test_str(self, finished):
        ledger = ProductionLedger.objects.create(
            product=finished,
            quantity=10,
            value=Decimal("100.00"),
            transaction_id=1,
        )
        assert str(finished) in str(ledger)

    def test_clean_negative_value_rejected(self, finished):
        ledger = ProductionLedger(
            product=finished,
            quantity=5,
            value=Decimal("-1.00"),
            transaction_id=1,
        )
        with pytest.raises(ValidationError, match="negative"):
            ledger.clean()
