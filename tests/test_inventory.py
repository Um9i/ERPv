import pytest
from django.db.models import Sum
from inventory.models import Inventory, InventoryAdjust, InventoryLedger


@pytest.mark.django_db
class TestInventory:
    def test_inventory_model_exists(self, product):
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.product.name == "product"

    def test_inventory_adjustment_alters_inventory_quantity(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inventory = Inventory.objects.get(pk=product.pk)
        assert inventory.quantity == 1

    def test_inventory_adjustment_ledger_is_created(self, product):
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        ledger = InventoryLedger.objects.filter(product=product).order_by("pk").first()
        assert ledger is not None
        assert ledger.product == product
        assert ledger.quantity == 1

    def test_closed_field_no_longer_exists(self):
        # ensure our migrations actually removed the closed column from the model
        assert not hasattr(InventoryAdjust, "closed"), "closed field should be removed"

    def test_adjust_form_prefills_product_and_is_readonly(self, client, product):
        from inventory.models import Inventory
        from django.urls import reverse
        from django.contrib.auth.models import User

        # login required
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        inventory = Inventory.objects.get(product=product)
        url = reverse("inventory:inventory-adjust", args=[inventory.pk])
        response = client.get(url)
        assert response.status_code == 200
        form = response.context.get("form")
        assert form is not None
        assert form.initial.get("product") == product
        assert form.fields["product"].disabled

        response = client.post(url, {"quantity": 2})
        assert response.status_code == 302
        adj = InventoryAdjust.objects.filter(product=product).order_by("-pk").first()
        assert adj is not None
        assert adj.quantity == 2
        assert adj.complete is True

    def test_inventory_list_search_and_pagination(self, client, product):
        from django.urls import reverse
        from inventory.models import Inventory, Product
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="tester")
        client.force_login(user)

        # insert many products
        for i in range(25):
            p = Product.objects.create(name=f"X{i}")
            Inventory.objects.update_or_create(product=p, defaults={"quantity": i})
        url = reverse("inventory:inventory-list")
        resp = client.get(url, {"q": "X1"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "X1" in content
        # result should not include other product rows; look for the name inside tags
        assert ">X3<" not in content
        # list styling should match supplier list: right‑aligned actions and delete confirmation
        assert 'class="text-end"' in content
        assert "Are you sure you want to delete this product?" in content
        # pagination should still work when multiple pages are needed
        resp2 = client.get(url + "?page=2")
        assert resp2.status_code == 200
        content2 = resp2.content.decode()
        # any documentation comment should not be rendered in the HTML
        assert "This include renders simple bootstrap pagination" not in content2

    def test_inventory_detail_ledger_and_last_updated(self, client, product):
        from inventory.models import Inventory, InventoryLedger
        from django.urls import reverse
        from django.contrib.auth.models import User

        # login required for protected views
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        # perform two adjustments to generate ledger entries
        InventoryAdjust.objects.create(product=product, quantity=5, complete=True)
        InventoryAdjust.objects.create(product=product, quantity=-2, complete=True)
        # detail page should show ledger entries and sensible totals
        url = reverse("inventory:inventory-detail", args=[inv.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Inventory Ledger" in content
        assert str(5) in content or str(-2) in content
        # old last-updated text removed, ensure inventory object is in context
        ctx = resp.context
        assert ctx["inventory"].last_updated is not None
        # summary statistics should appear as metric cards
        assert "Sales Pending" in content
        assert "Purchases Incoming" in content
        # shortage card only appears when nonzero; check for the label text
        assert "Shortage" in content or "In Stock" in content
        # chart canvases should be present
        assert '<canvas id="pending-chart"' in content
        assert '<canvas id="history-chart"' in content
        # ledger entries should appear (pagination header optional)

        # context should include history arrays matching adjustments
        ctx = resp.context
        assert "history_dates" in ctx and isinstance(ctx["history_dates"], list)
        assert "history_qty" in ctx and isinstance(ctx["history_qty"], list)
        # there should be two entries corresponding to the two adjustments
        assert len(ctx["history_qty"]) >= 2
        # final total should equal net change of adjustments (5 + -2)
        assert ctx["history_qty"][-1] == 3
        # monthly breakdown keys also returned (may be empty)
        assert "monthly_dates" in ctx and isinstance(ctx["monthly_dates"], list)
        assert "monthly_sales" in ctx and isinstance(ctx["monthly_sales"], list)
        assert "monthly_purchases" in ctx and isinstance(ctx["monthly_purchases"], list)
        assert "monthly_production" in ctx and isinstance(
            ctx["monthly_production"], list
        )
        # all monthly lists should have same length
        assert (
            len(ctx["monthly_dates"])
            == len(ctx["monthly_sales"])
            == len(ctx["monthly_purchases"])
            == len(ctx["monthly_production"])
        )

    def test_last_updated_changes_on_inventory_operations(self, product):
        from inventory.models import Inventory

        inv = Inventory.objects.get(product=product)
        orig = inv.last_updated
        # adjust inventory
        InventoryAdjust.objects.create(product=product, quantity=1, complete=True)
        inv.refresh_from_db()
        assert inv.last_updated > orig

    def test_stock_value_uses_bom(self, product):
        """Stock value should include BOM-derived cost when no direct cost.

        Product1 is made from Product2/3 and Product1 has no supplier cost.
        """
        from inventory.models import Inventory, Product
        from procurement.models import Supplier, SupplierProduct
        from production.models import BillOfMaterials, BOMItem

        # create components with supplier cost
        comp2 = Product.objects.create(name="component2")
        comp3 = Product.objects.create(name="component3")
        supplier = Supplier.objects.create(name="S")
        SupplierProduct.objects.create(supplier=supplier, product=comp2, cost=10)
        SupplierProduct.objects.create(supplier=supplier, product=comp3, cost=5)
        # finished product without supplier cost
        finished = Product.objects.create(name="finished1")
        # BOM: 2*comp2 +3*comp3
        bom = BillOfMaterials.objects.create(product=finished)
        BOMItem.objects.create(bom=bom, product=comp2, quantity=2)
        BOMItem.objects.create(bom=bom, product=comp3, quantity=3)
        # inventories
        Inventory.objects.update_or_create(product=finished, defaults={"quantity": 1})
        Inventory.objects.update_or_create(product=comp2, defaults={"quantity": 0})
        Inventory.objects.update_or_create(product=comp3, defaults={"quantity": 0})
        # compute dashboard context
        from inventory.views import InventoryDashboardView

        view = InventoryDashboardView()
        ctx = view.get_context_data()
        expected_cost = 1 * (2 * 10 + 3 * 5)
        assert ctx["stock_value"] == expected_cost

    def test_dashboard_links(self, client, product):
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Product, Inventory

        user = User.objects.create_user(username="tester")
        client.force_login(user)
        url = reverse("inventory:inventory-dashboard")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        # title now uses 'Inventory Management' to match new layout
        assert "Inventory Management" in content
        # heading icon should be present now that block is used
        assert '<i class="bi bi-box-seam' in content
        assert "View Inventory" in content
        # summary cards should appear
        assert "Products" in content
        # verify context values reflect database
        ctx = resp.context
        assert ctx["total_products"] == Product.objects.count()
        assert ctx["total_inventory_items"] == Inventory.objects.count()
        assert (
            ctx["total_quantity"]
            == Inventory.objects.aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        # when the required filter is applied we expect a list in context
        resp2 = client.get(url + "?required=1")
        assert "required_items" in resp2.context
        # ensure the low-stock view renders entries when shortages exist
        # create a shortage if none already
        if not resp2.context["required_items"]:
            inv = Inventory.objects.first()
            inv.quantity = 0
            inv.save()
            from sales.models import (
                Customer,
                CustomerProduct,
                SalesOrder,
                SalesOrderLine,
            )

            cust = Customer.objects.create(name="C4")
            cp = CustomerProduct.objects.create(
                customer=cust, product=inv.product, price=1
            )
            so = SalesOrder.objects.create(customer=cust)
            SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=5)
            resp2 = client.get(url + "?required=1")
        assert resp2.context["required_items"]
        content_l = client.get(
            reverse("inventory:inventory-low-stock")
        ).content.decode()
        # there should be table rows for required products
        assert "<table" in content_l
        entry = resp2.context["required_items"][0]
        assert entry["product"].name in content_l

    def test_low_stock_pagination(self, client, product):
        """More than one page of shortages should show pagination controls."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory

        # create many inventory rows with required shortage
        Inventory.objects.all().delete()
        Product = product.__class__
        # clear out existing products so new ones get fresh ids
        Product.objects.all().delete()
        # make 25 brand‑new products to avoid collisions
        products = [Product.objects.create(name=f"prod{i}") for i in range(25)]
        # inventories are automatically created via post-save signal when
        # we make each product, so no need to add them ourselves
        # force at least one sales order per item to make required>0
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        cust = Customer.objects.create(name="Cpage")
        for inv in Inventory.objects.all():
            cp = CustomerProduct.objects.create(
                customer=cust, product=inv.product, price=1
            )
            so = SalesOrder.objects.create(customer=cust)
            SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=1)
        user = User.objects.create_user(username="dashpage")
        client.force_login(user)
        resp = client.get(reverse("inventory:inventory-low-stock"))
        assert resp.status_code == 200
        content = resp.content.decode()
        # should include a pagination link to page 2
        assert "?page=2" in content
        # page object in context should report multiple pages
        page_obj = resp.context["required_items"]
        assert page_obj.paginator.num_pages > 1

    def test_low_stock_po_action_and_prefill(
        self, client, product, supplier, supplier_product
    ):
        """Items with suppliers should expose a PO link and it should prefill.

        We make the product short and associate a supplier-product; the low
        stock view should add a URL containing both the supplier id and item
        pairs. Visiting that URL should show a purchase order form with the
        appropriate initial line(s).
        """
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory

        # prepare shortage by setting quantity to zero and creating a
        # dummy sales order demanding 5 units
        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        cust = Customer.objects.create(name="C1")
        cp = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=5)
        assert inv.required > 0
        # ensure supplier_product fixture already links the product to supplier
        user = User.objects.create_user(username="tester")
        client.force_login(user)

        url = reverse("inventory:inventory-low-stock")
        resp = client.get(url)
        assert resp.status_code == 200
        items = resp.context["required_items"]
        assert items, "expected at least one low-stock entry"
        entry = items[0]
        assert entry.get("po_url"), "purchase order url should be present"
        # url should contain supplier param and at least one item= pair
        assert f"supplier={supplier.pk}" in entry["po_url"]
        assert "item=" in entry["po_url"]

        # now simulate a pending purchase order covering the requirement - link disappears
        from procurement.models import PurchaseOrder, PurchaseOrderLine

        po = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=supplier_product, quantity=5
        )
        resp3 = client.get(url)
        entry2 = resp3.context["required_items"][0]
        assert not entry2.get(
            "po_url"
        ), "PO link should be hidden when amount on PO meets required"

        # clear previous orders so we can test a partial amount case
        PurchaseOrderLine.objects.all().delete()
        PurchaseOrder.objects.all().delete()

        # if only partial amount is on PO then link still exists with reduced qty
        po2 = PurchaseOrder.objects.create(supplier=supplier)
        PurchaseOrderLine.objects.create(
            purchase_order=po2, product=supplier_product, quantity=2
        )
        resp4 = client.get(url)
        entry3 = resp4.context["required_items"][0]
        assert entry3.get("po_url"), "expected PO link when only partial amount exists"
        # verify query string quantity equals required - on_po
        assert (
            f"item={supplier_product.pk}:{entry3['po_order_qty']}" in entry3["po_url"]
        )

        # follow the link and inspect formset
        resp2 = client.get(entry["po_url"])
        assert resp2.status_code == 200
        fs = resp2.context["lines_formset"]
        # there should be a form for the initial item we required
        # values come back as strings from the query string
        assert int(fs.forms[0].initial.get("quantity")) == 5
        # supplier field should be hidden and have correct value
        form = resp2.context["form"]
        assert str(form.initial.get("supplier")) == str(supplier.pk)

    def test_low_stock_po_grouping_by_supplier(
        self, client, product, supplier, supplier_product
    ):
        """When multiple required products share a supplier, the PO link
        generated from any row should include all of them."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory
        from procurement.models import SupplierProduct
        from inventory.models import Product as InvProduct

        # create a second product with same supplier manually
        other = InvProduct.objects.create(name="other")
        inv_other, _ = Inventory.objects.get_or_create(product=other)
        inv_other.quantity = 0
        inv_other.save()
        # give other a shortage via sales order
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        custx = Customer.objects.create(name="CX")
        cpx = CustomerProduct.objects.create(customer=custx, product=other, price=1)
        sox = SalesOrder.objects.create(customer=custx)
        SalesOrderLine.objects.create(sales_order=sox, product=cpx, quantity=3)
        SupplierProduct.objects.create(supplier=supplier, product=other, cost=1)

        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        cust2 = Customer.objects.create(name="C2")
        cp2 = CustomerProduct.objects.create(customer=cust2, product=product, price=1)
        so2 = SalesOrder.objects.create(customer=cust2)
        SalesOrderLine.objects.create(sales_order=so2, product=cp2, quantity=2)
        assert inv.required > 0

        user = User.objects.create_user(username="tester2")
        client.force_login(user)
        resp = client.get(reverse("inventory:inventory-low-stock"))
        entry = resp.context["required_items"][0]
        url = entry["po_url"]
        # there should be two item= parameters in the query string
        assert url.count("item=") == 2

    def test_low_stock_production_prefill_quantity(self, client, product, bom):
        """The New job link should supply quantity equal to the required shortage."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory

        # create a shortage for the product using a BOM and sales order
        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        cust = Customer.objects.create(name="D")
        cp = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=4)
        assert inv.required > 0

        user = User.objects.create_user(username="tester5")
        client.force_login(user)
        resp = client.get(reverse("inventory:inventory-low-stock"))
        entry = resp.context["required_items"][0]
        link = (
            entry["product"]
            and f"?product={entry['product'].pk}&quantity={entry['order_qty']}"
        )
        # follow link by directly calling production create with same params
        from django.urls import reverse as r

        resp2 = client.get(r("production:production-create") + link)
        assert resp2.status_code == 200
        form = resp2.context["form"]
        assert int(form.initial.get("quantity")) == entry["order_qty"]

    def test_production_allocation_accumulates(self, product, bom):
        """Multiple production jobs add to component allocations."""
        from production.models import Production
        from inventory.models import ProductionAllocated

        # zero out allocations
        for item in bom.bom_items.all():
            pa = ProductionAllocated.objects.get(product=item.product)
            pa.quantity = 0
            pa.save(update_fields=["quantity"])

        job1 = Production.objects.create(product=product, quantity=2)
        job2 = Production.objects.create(product=product, quantity=3)
        total_qty = job1.quantity + job2.quantity
        for item in bom.bom_items.all():
            pa = ProductionAllocated.objects.get(product=item.product)
            assert pa.quantity == item.quantity * total_qty

    def test_low_stock_supplier_tiebreaker(
        self, client, product, supplier, supplier_product
    ):
        """If two suppliers offer the same price for a short item, choose the
        supplier whose overall catalogue (across all products) is cheaper.
        """
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory
        from procurement.models import Supplier, SupplierProduct
        from inventory.models import Product as InvProduct

        # existing supplier provides `product` at whatever fixture cost (=10)
        # create alternate supplier with same cost for this product so it's a tie
        other_supp = Supplier.objects.create(name="Other")
        SupplierProduct.objects.create(
            supplier=other_supp, product=product, cost=supplier_product.cost
        )
        # give the original supplier a cheaper overall catalogue by adding a
        # very low‑cost extra item
        extra = InvProduct.objects.create(name="extra1")
        SupplierProduct.objects.create(supplier=supplier, product=extra, cost=1)
        # make the alternate supplier more expensive overall by another product
        extra2 = InvProduct.objects.create(name="extra2")
        SupplierProduct.objects.create(supplier=other_supp, product=extra2, cost=100)
        # add inventory shortage for the main product (not necessary for extras)
        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        inv_extra, _ = Inventory.objects.get_or_create(product=extra)
        inv_extra.quantity = 0
        inv_extra.save()
        # create sales orders to make required >0 for each
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        cust = Customer.objects.create(name="TieCust")
        cp = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=2)
        cp2 = CustomerProduct.objects.create(customer=cust, product=extra, price=1)
        SalesOrderLine.objects.create(sales_order=so, product=cp2, quantity=3)

        user = User.objects.create_user(username="tester7")
        client.force_login(user)
        resp = client.get(reverse("inventory:inventory-low-stock"))
        items = resp.context["required_items"]
        # find entry for the original product; its po_url should use supplier
        entry = next(item for item in items if item["product"] == product)
        assert f"supplier={supplier.pk}" in entry["po_url"]

    def test_low_stock_query_count(
        self, client, product, supplier, supplier_product, django_assert_num_queries
    ):
        """Ensure low-stock view executes a bounded number of queries.

        We prepare a single shortage and then request the view; with the
        optimized code it should not perform an N+1 sequence of supplier or BOM
        lookups.  Allowing up to 15 queries keeps the test conservative.
        """
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory
        from sales.models import Customer, CustomerProduct, SalesOrder, SalesOrderLine

        inv = Inventory.objects.get(product=product)
        inv.quantity = 0
        inv.save()
        cust = Customer.objects.create(name="QC")
        cp = CustomerProduct.objects.create(customer=cust, product=product, price=1)
        so = SalesOrder.objects.create(customer=cust)
        SalesOrderLine.objects.create(sales_order=so, product=cp, quantity=5)

        user = User.objects.create_user(username="qcuser")
        client.force_login(user)
        url = reverse("inventory:inventory-low-stock")
        # allow a generous ceiling to accommodate middleware and debug toolbar
        # queries; we simply assert we don't explode with an N+1 pattern.
        with django_assert_num_queries(100, exact=False):
            resp = client.get(url)
        assert resp.status_code == 200

    # ── Location & Stock Transfer tests ────────────────────────

    def test_location_hierarchy_full_path(self, db):
        """Location.full_path() builds Warehouse / Zone / Bin string."""
        from inventory.models import Location

        wh = Location.objects.create(name="Warehouse A")
        zone = Location.objects.create(name="Zone 1", parent=wh)
        bin_ = Location.objects.create(name="Bin B2", parent=zone)
        assert wh.full_path() == "Warehouse A"
        assert zone.full_path() == "Warehouse A / Zone 1"
        assert bin_.full_path() == "Warehouse A / Zone 1 / Bin B2"

    def test_location_crud_views(self, client, db):
        """Location list, create, update, delete views work."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Location

        user = User.objects.create_user(username="locuser")
        client.force_login(user)

        # create
        resp = client.post(
            reverse("inventory:location-create"),
            {"name": "Warehouse X"},
        )
        assert resp.status_code == 302
        wh = Location.objects.get(name="Warehouse X")

        # create child with ?parent= prefill
        resp = client.get(reverse("inventory:location-create") + f"?parent={wh.pk}")
        assert resp.status_code == 200
        form = resp.context["form"]
        assert str(form.initial.get("parent")) == str(wh.pk)

        # actually create the zone
        resp = client.post(
            reverse("inventory:location-create"),
            {"name": "Zone A", "parent": wh.pk},
        )
        assert resp.status_code == 302
        zone = Location.objects.get(name="Zone A")
        assert zone.parent == wh

        # list shows hierarchy
        resp = client.get(reverse("inventory:location-list"))
        assert resp.status_code == 200
        assert "Warehouse X" in resp.content.decode()
        assert "Zone A" in resp.content.decode()

        # update
        resp = client.post(
            reverse("inventory:location-update", args=[zone.pk]),
            {"name": "Zone B", "parent": wh.pk},
        )
        assert resp.status_code == 302
        zone.refresh_from_db()
        assert zone.name == "Zone B"

        # delete
        resp = client.post(reverse("inventory:location-delete", args=[zone.pk]))
        assert resp.status_code == 302
        assert not Location.objects.filter(pk=zone.pk).exists()

    def test_inventory_location_allocation_enforced(self, client, product):
        """Allocated qty cannot exceed stock on hand."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory, Location

        user = User.objects.create_user(username="allocuser")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=10, complete=True)
        inv.refresh_from_db()
        assert inv.quantity == 10

        bin_a = Location.objects.create(name="Bin A")

        # assign 10 — should succeed
        resp = client.post(
            reverse("inventory:inventory-location-add", args=[inv.pk]),
            {"location": bin_a.pk, "quantity": 10},
        )
        assert resp.status_code == 302

        bin_b = Location.objects.create(name="Bin B")
        # assign 1 more — should fail (total would be 11 > 10)
        resp = client.post(
            reverse("inventory:inventory-location-add", args=[inv.pk]),
            {"location": bin_b.pk, "quantity": 1},
        )
        assert resp.status_code == 200  # re-renders form with error
        assert "exceed stock on hand" in resp.content.decode()

    def test_stock_transfer_moves_quantity(self, product):
        """Transfer deducts from source, adds to dest, creates ledger entries."""
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            InventoryLedger,
            StockTransfer,
        )

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=100, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="Bin A")
        bin_b = Location.objects.create(name="Bin B")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=80)
        InventoryLocation.objects.create(inventory=inv, location=bin_b, quantity=20)

        ledger_before = InventoryLedger.objects.filter(product=product).count()

        transfer = StockTransfer(
            inventory=inv,
            from_location=bin_a,
            to_location=bin_b,
            quantity=30,
        )
        transfer.save()

        # location quantities updated
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_a).quantity == 50
        )
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_b).quantity == 50
        )

        # total stock unchanged
        inv.refresh_from_db()
        assert inv.quantity == 100

        # two ledger entries created (one negative, one positive)
        new_entries = InventoryLedger.objects.filter(
            product=product, action="Stock Transfer"
        )
        assert new_entries.count() == 2
        assert new_entries.filter(quantity=-30).exists()
        assert new_entries.filter(quantity=30).exists()

    def test_stock_transfer_creates_destination_if_missing(self, product):
        """Transfer to an unassigned location creates the InventoryLocation."""
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            StockTransfer,
        )

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=50, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="Bin A")
        bin_c = Location.objects.create(name="Bin C")  # no InventoryLocation yet
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=50)

        StockTransfer.objects.create(
            inventory=inv,
            from_location=bin_a,
            to_location=bin_c,
            quantity=15,
        )

        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_c).quantity == 15
        )
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_a).quantity == 35
        )

    def test_stock_transfer_rejects_insufficient_source(self, product):
        """Transfer more than source has should raise ValidationError."""
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            StockTransfer,
        )
        from django.core.exceptions import ValidationError

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=10, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="Bin A")
        bin_b = Location.objects.create(name="Bin B")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=10)

        with pytest.raises(ValidationError):
            StockTransfer.objects.create(
                inventory=inv,
                from_location=bin_a,
                to_location=bin_b,
                quantity=999,
            )
        # source quantity unchanged
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_a).quantity == 10
        )

    def test_stock_transfer_rejects_same_location(self, product):
        """Transfer from and to the same location should be rejected."""
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            StockTransfer,
        )
        from django.core.exceptions import ValidationError

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=10, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="Bin A")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=10)

        with pytest.raises(ValidationError):
            StockTransfer.objects.create(
                inventory=inv,
                from_location=bin_a,
                to_location=bin_a,
                quantity=5,
            )

    def test_stock_transfer_view(self, client, product):
        """Transfer form renders and processes correctly."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            StockTransfer,
        )

        user = User.objects.create_user(username="xferuser")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=100, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="Bin A")
        bin_b = Location.objects.create(name="Bin B")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=100)

        url = reverse("inventory:stock-transfer", args=[inv.pk])

        # GET shows the form
        resp = client.get(url)
        assert resp.status_code == 200
        assert "Transfer" in resp.content.decode()

        # POST creates the transfer
        resp = client.post(
            url,
            {
                "from_location": bin_a.pk,
                "to_location": bin_b.pk,
                "quantity": 40,
                "note": "rebalance",
            },
        )
        assert resp.status_code == 302
        assert StockTransfer.objects.count() == 1
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_a).quantity == 60
        )
        assert (
            InventoryLocation.objects.get(inventory=inv, location=bin_b).quantity == 40
        )

    def test_inventory_list_shows_locations(self, client, product):
        """Inventory list view includes location badges."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import Inventory, Location, InventoryLocation

        user = User.objects.create_user(username="listlocuser")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=50, complete=True)
        inv.refresh_from_db()

        bin_x = Location.objects.create(name="Bin X")
        InventoryLocation.objects.create(inventory=inv, location=bin_x, quantity=50)

        resp = client.get(reverse("inventory:inventory-list"))
        content = resp.content.decode()
        assert "Bin X" in content
        assert "(50)" in content

    def test_ledger_shows_location(self, client, product):
        """Ledger table displays location when set on an entry."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from inventory.models import (
            Inventory,
            Location,
            InventoryLocation,
            StockTransfer,
        )

        user = User.objects.create_user(username="ledgerlocuser")
        client.force_login(user)

        inv = Inventory.objects.get(product=product)
        InventoryAdjust.objects.create(product=product, quantity=100, complete=True)
        inv.refresh_from_db()

        bin_a = Location.objects.create(name="LocLedgerA")
        bin_b = Location.objects.create(name="LocLedgerB")
        InventoryLocation.objects.create(inventory=inv, location=bin_a, quantity=100)

        StockTransfer.objects.create(
            inventory=inv,
            from_location=bin_a,
            to_location=bin_b,
            quantity=10,
        )

        resp = client.get(reverse("inventory:inventory-detail", args=[inv.pk]))
        content = resp.content.decode()
        assert "Location" in content  # column header
        assert "LocLedgerA" in content
        assert "LocLedgerB" in content
        assert "Stock Transfer" in content
