from django.test import TestCase
from inventory.models import Product
from manufacturing.models import BillOfMaterials, BOMItem, Job


class BOMTestCase(TestCase):
    def setUp(self):
        Product.objects.create(name="product 1", quantity=0.00)
        Product.objects.create(name="product 2", quantity=10.00)
        Product.objects.create(name="product 3", quantity=5.00)
        self.product1 = Product.objects.get(name="product 1")
        self.product2 = Product.objects.get(name="product 2")
        self.product3 = Product.objects.get(name="product 3")
        BillOfMaterials.objects.create(product=self.product1, labour_cost=0.00)
        bom = BillOfMaterials.objects.get(product=self.product1)
        BOMItem.objects.create(bom=bom, product=self.product2, quantity=1.00)
        BOMItem.objects.create(bom=bom, product=self.product3, quantity=1.00)
        Job.objects.create(pk=1, product=self.product1, quantity=10.00, priority=1)
        self.job = Job.objects.get(pk=1)

    def test_bill_of_materials(self):
        product1 = Product.objects.get(name="product 1")
        product2 = Product.objects.get(name="product 2")
        product3 = Product.objects.get(name="product 3")
        self.assertEqual(product1.quantity, 0.00)
        self.assertEqual(product2.quantity, 10.00)
        self.assertEqual(product3.quantity, 5.00)
        self.job.bom_allocated = True
        self.job.save()
        self.assertEqual(product1.planned(), 10.00)
        self.assertEqual(product2.required(), 0.00)
        self.assertEqual(product3.required(), 5.00)
        self.job.complete = True
        self.job.save()
        product1 = Product.objects.get(name="product 1")
        product2 = Product.objects.get(name="product 2")
        product3 = Product.objects.get(name="product 3")
        self.assertEqual(product1.quantity, 10.00)
        self.assertEqual(product2.quantity, 0.00)
        self.assertEqual(product3.quantity, -5.00)
        bom = BillOfMaterials.objects.get(product=product1)
        self.assertEqual(bom.__str__(), "product 1")
        self.assertEqual(bom.total_cost(), 0.00)

    def test_products_bill_of_materials_cannot_inception(self):
        BillOfMaterials.objects.create(product=self.product2, labour_cost=0.00)
        bom = BillOfMaterials.objects.get(product=self.product2)
        BOMItem.objects.create(bom=bom, product=self.product2, quantity=1.00)
        self.assertTrue(len(bom.bom_items.all()), 0)
