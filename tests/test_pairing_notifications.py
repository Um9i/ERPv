import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from config.models import PairedInstance
from inventory.models import Product
from sales.models import Customer, CustomerProduct


class NotifyCustomerViewTest(TestCase):

    def setUp(self):
        self.instance = PairedInstance.objects.create(
            name="Remote Partner",
            url="https://remote.example.com",
            api_key="their-key",
        )
        self.url = reverse("config:notify-customer")
        self.payload = {
            "name": "Remote Co Ltd",
            "address_line_1": "1 Remote St",
            "city": "Remoteville",
            "postal_code": "RM1 1AA",
            "country": "GB",
            "phone": "01234 567890",
            "email": "info@remote.example.com",
            "website": "https://remote.example.com",
        }

    def _post(self, payload, key=None):
        token = key if key is not None else self.instance.our_key
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_no_auth_returns_401(self):
        response = self.client.post(
            self.url, data=json.dumps(self.payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_key_returns_401(self):
        response = self._post(self.payload, key="totally-wrong-key")
        self.assertEqual(response.status_code, 401)

    def test_creates_customer_and_links_to_paired_instance(self):
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["created"])

        customer = Customer.objects.get(name="Remote Co Ltd")
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.customer, customer)

    def test_reuses_existing_customer_without_duplicate(self):
        existing = Customer.objects.create(name="Remote Co Ltd")
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["created"])
        self.assertEqual(
            Customer.objects.filter(name__iexact="Remote Co Ltd").count(), 1
        )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.customer, existing)

    def test_missing_name_returns_400(self):
        response = self._post({**self.payload, "name": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class NotifyCustomerProductViewTest(TestCase):

    def setUp(self):
        self.customer = Customer.objects.create(name="Linked Customer")
        self.instance = PairedInstance.objects.create(
            name="Remote Partner",
            url="https://remote.example.com",
            api_key="their-key",
            customer=self.customer,
        )
        self.product = Product.objects.create(
            name="Test Widget",
            sale_price=Decimal("10.00"),
        )
        self.url = reverse("config:notify-customer-product")
        self.payload = {"product_name": "Test Widget", "price": "9.99"}

    def _post(self, payload, key=None):
        token = key if key is not None else self.instance.our_key
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_customer_not_linked_returns_400(self):
        unlinked = PairedInstance.objects.create(
            name="Unlinked Partner",
            url="https://unlinked.example.com",
            api_key="key2",
        )
        response = self._post(self.payload, key=unlinked.our_key)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Customer not linked", response.json()["error"])

    def test_creates_customer_product_with_correct_price(self):
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["created"])

        cp = CustomerProduct.objects.get(customer=self.customer, product=self.product)
        self.assertEqual(cp.price, Decimal("9.99"))

    def test_updates_price_on_existing_customer_product(self):
        CustomerProduct.objects.create(
            customer=self.customer, product=self.product, price=Decimal("1.00")
        )
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["created"])

        cp = CustomerProduct.objects.get(customer=self.customer, product=self.product)
        self.assertEqual(cp.price, Decimal("9.99"))

    def test_product_not_found_returns_400(self):
        response = self._post(
            {"product_name": "Nonexistent Product XYZ", "price": "5.00"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Product not found", response.json()["error"])
