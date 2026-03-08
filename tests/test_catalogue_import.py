from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from config.models import PairedInstance
from inventory.models import Product
from procurement.models import Supplier, SupplierProduct


class ImportCatalogueProductViewTest(TestCase):

    def setUp(self):
        self.staff_user = User.objects.create_user(
            "staffimport", password="testpass123", is_staff=True
        )
        self.regular_user = User.objects.create_user(
            "regularimport", password="testpass123", is_staff=False
        )
        self.supplier = Supplier.objects.create(name="Remote Supplier Co")
        self.active_instance = PairedInstance.objects.create(
            name="Active Partner",
            url="https://active.example.com",
            api_key="real-api-key",
            supplier=self.supplier,
        )
        self.pending_instance = PairedInstance.objects.create(
            name="Pending Partner",
            url="https://pending.example.com",
            api_key="",
        )
        self.import_url = reverse(
            "config:paired-instance-import-product",
            args=[self.active_instance.pk],
        )
        self.post_data = {
            "name": "Remote Widget",
            "description": "A widget from remote",
            "sale_price": "9.99",
            "supplier_id": str(self.supplier.pk),
        }

    def _login_staff(self):
        self.client.login(username="staffimport", password="testpass123")

    # --- access control ---

    def test_import_view_requires_login(self):
        response = self.client.post(self.import_url, self.post_data)
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Remote Widget").exists())

    def test_import_view_is_staff_only(self):
        self.client.login(username="regularimport", password="testpass123")
        response = self.client.post(self.import_url, self.post_data)
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Remote Widget").exists())

    # --- pending instance ---

    def test_pending_instance_redirects_to_list_with_error(self):
        self._login_staff()
        pending_url = reverse(
            "config:paired-instance-import-product",
            args=[self.pending_instance.pk],
        )
        response = self.client.post(
            pending_url,
            {**self.post_data, "supplier_id": str(self.supplier.pk)},
        )
        self.assertRedirects(response, reverse("config:paired-instance-list"))
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any(m.tags == "error" for m in messages))

    # --- invalid supplier ---

    def test_invalid_supplier_id_returns_error(self):
        self._login_staff()
        response = self.client.post(
            self.import_url,
            {**self.post_data, "supplier_id": "999999"},
        )
        browse_url = reverse(
            "config:paired-instance-browse-catalogue",
            args=[self.active_instance.pk],
        )
        self.assertRedirects(response, browse_url)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any(m.tags == "error" for m in messages))

    # --- happy path: new product and supplier product created ---

    def test_import_creates_new_product_and_supplier_product(self):
        self._login_staff()
        response = self.client.post(self.import_url, self.post_data)
        browse_url = reverse(
            "config:paired-instance-browse-catalogue",
            args=[self.active_instance.pk],
        )
        self.assertRedirects(response, browse_url)

        product = Product.objects.get(name="Remote Widget")
        self.assertEqual(product.description, "A widget from remote")
        self.assertEqual(product.sale_price, Decimal("9.99"))

        sp = SupplierProduct.objects.get(supplier=self.supplier, product=product)
        self.assertEqual(sp.cost, Decimal("9.99"))

    # --- imported product does not get catalogue_item=True ---

    def test_imported_product_does_not_have_catalogue_item_true(self):
        self._login_staff()
        self.client.post(self.import_url, self.post_data)
        product = Product.objects.get(name="Remote Widget")
        self.assertFalse(product.catalogue_item)

    # --- reuse existing product by name (case-insensitive) ---

    def test_import_reuses_existing_product_without_overwriting(self):
        existing = Product.objects.create(
            name="Remote Widget",
            description="Original description",
            sale_price=Decimal("5.00"),
        )
        self._login_staff()
        self.client.post(self.import_url, self.post_data)

        # Should still be only one product with that name
        self.assertEqual(
            Product.objects.filter(name__iexact="Remote Widget").count(), 1
        )
        existing.refresh_from_db()
        # Fields must not have been overwritten
        self.assertEqual(existing.description, "Original description")
        self.assertEqual(existing.sale_price, Decimal("5.00"))

    # --- update cost on existing SupplierProduct ---

    def test_import_updates_cost_on_existing_supplier_product(self):
        product = Product.objects.create(
            name="Remote Widget", sale_price=Decimal("5.00")
        )
        SupplierProduct.objects.create(
            supplier=self.supplier, product=product, cost=Decimal("1.00")
        )
        self._login_staff()
        self.client.post(self.import_url, self.post_data)

        sp = SupplierProduct.objects.get(supplier=self.supplier, product=product)
        self.assertEqual(sp.cost, Decimal("9.99"))
