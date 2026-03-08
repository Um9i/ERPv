from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from config.models import PairedInstance, CompanyConfig


class PairedInstanceModelTest(TestCase):

    def test_our_key_auto_generated_on_save(self):
        instance = PairedInstance.objects.create(
            name="Test Partner",
            url="https://partner.example.com",
            api_key="their-key-abc",
        )
        self.assertTrue(instance.our_key)
        self.assertGreater(len(instance.our_key), 0)

    def test_our_key_not_overwritten_if_provided(self):
        instance = PairedInstance.objects.create(
            name="Test Partner",
            url="https://partner.example.com",
            api_key="their-key-abc",
            our_key="fixed-custom-key",
        )
        self.assertEqual(instance.our_key, "fixed-custom-key")

    def test_our_key_preview_shows_first_8_chars(self):
        instance = PairedInstance(our_key="abcdefghijklmnop")
        self.assertEqual(instance.our_key_preview, "abcdefgh\u2026")


class CompanyApiViewTest(TestCase):

    def setUp(self):
        self.instance = PairedInstance.objects.create(
            name="Partner Co",
            url="https://partner.example.com",
            api_key="their-key-xyz",
        )
        CompanyConfig.objects.create(
            name="My Company Ltd",
            address_line_1="1 High Street",
            city="London",
            postal_code="SW1A 1AA",
            country="GB",
            phone="01234567890",
            email="info@mycompany.example.com",
            vat_number="GB123456789",
            company_number="12345678",
        )

    def test_no_auth_header_returns_401(self):
        response = self.client.get(reverse("config:company-api"))
        self.assertEqual(response.status_code, 401)

    def test_wrong_key_returns_401(self):
        response = self.client.get(
            reverse("config:company-api"),
            HTTP_AUTHORIZATION="Bearer totally-wrong-key",
        )
        self.assertEqual(response.status_code, 401)

    def test_malformed_auth_header_returns_401(self):
        response = self.client.get(
            reverse("config:company-api"),
            HTTP_AUTHORIZATION="Token not-bearer",
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_key_returns_200_with_company_data(self):
        response = self.client.get(
            reverse("config:company-api"),
            HTTP_AUTHORIZATION=f"Bearer {self.instance.our_key}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "My Company Ltd")
        self.assertEqual(data["address_line_1"], "1 High Street")
        self.assertEqual(data["city"], "London")
        self.assertEqual(data["postal_code"], "SW1A 1AA")
        self.assertEqual(data["country"], "GB")
        self.assertIn("vat_number", data)
        self.assertIn("company_number", data)


class PairedInstanceListViewTest(TestCase):

    def setUp(self):
        self.staff_user = User.objects.create_user(
            "staffuser", password="testpass123", is_staff=True
        )
        self.regular_user = User.objects.create_user(
            "regularuser", password="testpass123", is_staff=False
        )

    def test_list_view_redirects_unauthenticated(self):
        response = self.client.get(reverse("config:paired-instance-list"))
        self.assertNotEqual(response.status_code, 200)

    def test_list_view_redirects_non_staff(self):
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("config:paired-instance-list"))
        self.assertNotEqual(response.status_code, 200)

    def test_list_view_accessible_by_staff(self):
        self.client.login(username="staffuser", password="testpass123")
        response = self.client.get(reverse("config:paired-instance-list"))
        self.assertEqual(response.status_code, 200)
