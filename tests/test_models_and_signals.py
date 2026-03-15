"""Tests covering inventory model properties, currency tag edge cases,
and config signals early-exit paths."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from inventory.models import Inventory, Product
from main.templatetags.currency_tags import currency
from procurement.models import Supplier, SupplierProduct
from production.models import BillOfMaterials, BOMItem

pytestmark = pytest.mark.integration


# ── Product.unit_cost ────────────────────────────────────────────────
class TestProductUnitCost:
    def test_no_supplier_no_bom(self, db):
        p = Product.objects.create(name="Bare Product")
        assert p.unit_cost == 0

    def test_with_supplier_cost(self, db):
        p = Product.objects.create(name="Supplied Part")
        s = Supplier.objects.create(name="Cost Sup")
        SupplierProduct.objects.create(supplier=s, product=p, cost=Decimal("7.50"))
        assert p.unit_cost == Decimal("7.50")

    def test_bom_cost_rollup(self, db):
        comp = Product.objects.create(name="BOM Comp")
        fin = Product.objects.create(name="BOM Finished")
        s = Supplier.objects.create(name="BOM Sup")
        SupplierProduct.objects.create(supplier=s, product=comp, cost=Decimal("4.00"))
        bom = BillOfMaterials.objects.create(
            product=fin, production_cost=Decimal("2.00")
        )
        BOMItem.objects.create(bom=bom, product=comp, quantity=3)
        # cost = 3 × 4.00 + 2.00 = 14.00
        assert fin.unit_cost == Decimal("14.00")


# ── Product.can_produce ──────────────────────────────────────────────
class TestCanProduce:
    def test_no_bom(self, db):
        p = Product.objects.create(name="No BOM")
        assert p.can_produce is False

    def test_insufficient_inventory(self, db):
        comp = Product.objects.create(name="CP Comp")
        fin = Product.objects.create(name="CP Finished")
        s = Supplier.objects.create(name="CP Sup")
        SupplierProduct.objects.create(supplier=s, product=comp, cost=Decimal("1"))
        bom = BillOfMaterials.objects.create(product=fin)
        BOMItem.objects.create(bom=bom, product=comp, quantity=5)
        Inventory.objects.filter(product=comp).update(quantity=2)
        assert fin.can_produce is False

    def test_sufficient_inventory(self, db):
        comp = Product.objects.create(name="CP Comp2")
        fin = Product.objects.create(name="CP Finished2")
        s = Supplier.objects.create(name="CP Sup2")
        SupplierProduct.objects.create(supplier=s, product=comp, cost=Decimal("1"))
        bom = BillOfMaterials.objects.create(product=fin)
        BOMItem.objects.create(bom=bom, product=comp, quantity=3)
        Inventory.objects.filter(product=comp).update(quantity=100)
        assert fin.can_produce is True


# ── Inventory.required ───────────────────────────────────────────────
class TestInventoryRequired:
    def test_required_zero_when_no_demand(self, db):
        p = Product.objects.create(name="No Demand")
        inv = Inventory.objects.get(product=p)
        assert inv.required == 0


# ── Currency tag ─────────────────────────────────────────────────────
@pytest.mark.unit
class TestCurrencyTag:
    def test_negative_value(self):
        result = currency(-1234.56)
        assert "-" in result
        assert "1,234.56" in result

    def test_invalid_value(self):
        assert currency("not-a-number") == "not-a-number"


# ── Config signals early returns ─────────────────────────────────────
class TestConfigSignalsEdgeCases:
    """Test that signal handlers exit early for new (unsaved) instances."""

    def test_sales_order_line_completion_signal_new_instance(self, db):
        """pre_save for SO line completed — no pk → no-op."""
        from config.signals import _notify_sales_order_completed
        from sales.models import SalesOrderLine

        instance = SalesOrderLine.__new__(SalesOrderLine)
        instance.pk = None
        # should not raise
        _notify_sales_order_completed(sender=SalesOrderLine, instance=instance)

    def test_purchase_order_line_completion_signal_new_instance(self, db):
        """pre_save for PO line completed — no pk → no-op."""
        from config.signals import _notify_purchase_order_received
        from procurement.models import PurchaseOrderLine

        instance = PurchaseOrderLine.__new__(PurchaseOrderLine)
        instance.pk = None
        _notify_purchase_order_received(sender=PurchaseOrderLine, instance=instance)

    def test_webhook_shipment_signal_no_pk(self, db):
        from config.signals import _webhook_shipment_completed
        from sales.models import SalesOrderLine

        instance = SalesOrderLine.__new__(SalesOrderLine)
        instance.pk = None
        _webhook_shipment_completed(sender=SalesOrderLine, instance=instance)

    def test_webhook_production_signal_no_pk(self, db):
        from config.signals import _webhook_production_completed
        from production.models import Production

        instance = Production.__new__(Production)
        instance.pk = None
        _webhook_production_completed(sender=Production, instance=instance)

    def test_webhook_order_created_not_created(self, db):
        """post_save with created=False → no-op."""
        from config.signals import _webhook_order_created
        from sales.models import SalesOrder

        instance = SalesOrder.__new__(SalesOrder)
        instance.pk = 999
        with patch("config.signals.dispatch_event") as mock:
            _webhook_order_created(sender=SalesOrder, instance=instance, created=False)
            mock.assert_not_called()

    def test_webhook_stock_adjusted_not_created(self, db):
        """post_save with created=False → no-op."""
        from config.signals import _webhook_stock_adjusted
        from inventory.models import InventoryAdjust

        instance = InventoryAdjust.__new__(InventoryAdjust)
        instance.pk = 999
        with patch("config.signals.dispatch_event") as mock:
            _webhook_stock_adjusted(
                sender=InventoryAdjust, instance=instance, created=False
            )
            mock.assert_not_called()
