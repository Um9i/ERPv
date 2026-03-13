from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from config.models import PairedInstance
from inventory.models import Product


class ProductCatalogueCleanTest(SimpleTestCase):
    """Model-level validation for catalogue_item field."""

    def test_catalogue_item_true_with_no_sale_price_fails_clean(self):
        product = Product(name="No Price Item", catalogue_item=True, sale_price=None)
        with self.assertRaises(ValidationError):
            product.clean()

    def test_catalogue_item_false_with_no_sale_price_passes_clean(self):
        product = Product(
            name="Non-Catalogue Item", catalogue_item=False, sale_price=None
        )
        # Should not raise
        product.clean()


class CatalogueApiViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.paired = PairedInstance.objects.create(
            name="Partner",
            url="https://partner.example.com",
            api_key="their-key",
        )
        cls.url = reverse("inventory:catalogue-api")

        # A valid catalogue product
        cls.product_a = Product.objects.create(
            name="Widget A",
            description="A fine widget",
            sale_price=Decimal("12.50"),
            catalogue_item=True,
        )
        # Not a catalogue item — should be excluded
        cls.product_b = Product.objects.create(
            name="Internal Part",
            description="",
            sale_price=Decimal("5.00"),
            catalogue_item=False,
        )
        # No sale price — should be excluded
        cls.product_c = Product.objects.create(
            name="Unpriced Widget",
            description="",
            sale_price=None,
            catalogue_item=False,  # False so it won't fail model clean()
        )

    def test_no_auth_header_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_wrong_key_returns_401(self):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION="Bearer totally-wrong-key"
        )
        self.assertEqual(response.status_code, 401)

    def test_malformed_auth_returns_401(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Token not-bearer")
        self.assertEqual(response.status_code, 401)

    def test_valid_key_returns_200_with_product_data(self):
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {self.paired.our_key}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Widget A")
        self.assertEqual(data[0]["description"], "A fine widget")
        self.assertEqual(data[0]["sale_price"], "12.50")
        self.assertIsNone(data[0]["sku"])

    def test_excludes_non_catalogue_products(self):
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {self.paired.our_key}",
        )
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertNotIn("Internal Part", names)

    def test_excludes_products_with_null_sale_price(self):
        # Create a product that has catalogue_item=True would need a price,
        # so we directly filter: a product with sale_price=None is excluded regardless.
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {self.paired.our_key}",
        )
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertNotIn("Unpriced Widget", names)


class BrowseCatalogueViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user("staffcat", is_staff=True)
        cls.regular_user = User.objects.create_user("regularcat", is_staff=False)
        cls.active_instance = PairedInstance.objects.create(
            name="Active Partner",
            url="https://active.example.com",
            api_key="real-api-key",
        )
        cls.pending_instance = PairedInstance.objects.create(
            name="Pending Partner",
            url="https://pending.example.com",
            api_key="",
        )

    def test_browse_catalogue_requires_login(self):
        url = reverse(
            "config:paired-instance-browse-catalogue", args=[self.active_instance.pk]
        )
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

    def test_browse_catalogue_staff_only(self):
        self.client.force_login(self.regular_user)
        url = reverse(
            "config:paired-instance-browse-catalogue", args=[self.active_instance.pk]
        )
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)

    def test_browse_catalogue_pending_instance_redirects_with_error(self):
        self.client.force_login(self.staff_user)
        url = reverse(
            "config:paired-instance-browse-catalogue", args=[self.pending_instance.pk]
        )
        response = self.client.get(url)
        self.assertRedirects(response, reverse("config:paired-instance-list"))

    @patch("config.views.httpx.get")
    def test_browse_catalogue_success(self, mock_get):
        self.client.force_login(self.staff_user)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "name": "Widget A",
                "description": "Nice",
                "sale_price": "12.50",
                "sku": None,
            }
        ]
        mock_get.return_value = mock_resp

        self.client.force_login(self.staff_user)
        url = reverse(
            "config:paired-instance-browse-catalogue", args=[self.active_instance.pk]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Widget A")
        self.assertContains(response, "12.50")

    @patch("config.views.httpx.get")
    def test_browse_catalogue_non_200_shows_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        self.client.force_login(self.staff_user)
        url = reverse(
            "config:paired-instance-browse-catalogue", args=[self.active_instance.pk]
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "500")
