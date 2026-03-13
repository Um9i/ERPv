import pytest
from django.test import TestCase

from config.models import CompanyConfig

pytestmark = pytest.mark.unit


class CompanyConfigSingletonTest(TestCase):
    def test_can_create_first_instance(self):
        obj = CompanyConfig.objects.create(name="ACME Ltd")
        self.assertEqual(obj.pk, 1)

    def test_cannot_create_second_instance(self):
        CompanyConfig.objects.create(name="ACME Ltd")
        with self.assertRaises(ValueError):
            CompanyConfig(name="Other Co").save()

    def test_pk_always_forced_to_1(self):
        obj = CompanyConfig(name="ACME Ltd")
        obj.save()
        self.assertEqual(obj.pk, 1)

    def test_get_returns_instance(self):
        CompanyConfig.objects.create(name="ACME Ltd")
        result = CompanyConfig.get()
        self.assertEqual(result.name, "ACME Ltd")

    def test_get_returns_none_when_empty(self):
        self.assertIsNone(CompanyConfig.get())

    def test_get_or_default_returns_unsaved_default(self):
        result = CompanyConfig.get_or_default()
        self.assertEqual(result.name, "ERPv")
        self.assertIsNone(result.pk)

    def test_delete_is_a_noop(self):
        obj = CompanyConfig.objects.create(name="ACME Ltd")
        obj.delete()
        self.assertTrue(CompanyConfig.objects.filter(pk=1).exists())
