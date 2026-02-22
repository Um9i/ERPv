import random
from datetime import timedelta
import factory
from faker import Faker
from django.utils import timezone

from inventory.models import Product, Inventory
from sales.models import (
    Customer,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
)
from procurement.models import (
    Supplier,
    SupplierProduct,
    PurchaseOrder,
    PurchaseOrderLine,
)
from production.models import (
    BillOfMaterials,
    BOMItem,
    Production,
)

fake = Faker()


import uuid

class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    # generate a UUID-based name so every invocation is globally unique
    name = factory.LazyFunction(lambda: f"Prod-{uuid.uuid4().hex[:8]}")


class InventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Inventory

    product = factory.SubFactory(ProductFactory)
    quantity = factory.LazyFunction(lambda: random.randint(0, 200))
    # do not attempt to set ``required`` property; it's computed


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    # ensure uniqueness to satisfy unique constraint
    name = factory.LazyFunction(lambda: f"Cust-{uuid.uuid4().hex[:8]}")
    address = factory.LazyAttribute(lambda x: fake.address())
    phone = factory.LazyAttribute(lambda x: fake.phone_number())
    email = factory.LazyAttribute(lambda x: fake.company_email())
    website = factory.LazyAttribute(lambda x: fake.url())


class CustomerProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomerProduct

    customer = factory.SubFactory(CustomerFactory)
    product = factory.SubFactory(ProductFactory)
    price = factory.LazyFunction(lambda: round(random.uniform(5, 500), 2))


class SalesOrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SalesOrder

    customer = factory.SubFactory(CustomerFactory)
    created_at = factory.LazyFunction(timezone.now)


class SalesOrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SalesOrderLine

    sales_order = factory.SubFactory(SalesOrderFactory)
    product = factory.SubFactory(CustomerProductFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 20))
    quantity_shipped = 0
    complete = False
    closed = False
    value = factory.LazyAttribute(lambda obj: obj.product.price * obj.quantity)


class SupplierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Supplier

    name = factory.LazyFunction(lambda: f"Supp-{uuid.uuid4().hex[:8]}")
    address = factory.LazyAttribute(lambda x: fake.address())
    phone = factory.LazyAttribute(lambda x: fake.phone_number())
    email = factory.LazyAttribute(lambda x: fake.company_email())
    website = factory.LazyAttribute(lambda x: fake.url())


class SupplierProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SupplierProduct

    supplier = factory.SubFactory(SupplierFactory)
    product = factory.SubFactory(ProductFactory)
    cost = factory.LazyFunction(lambda: round(random.uniform(1, 200), 2))


class PurchaseOrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PurchaseOrder

    supplier = factory.SubFactory(SupplierFactory)
    created_at = factory.LazyFunction(timezone.now)


class PurchaseOrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PurchaseOrderLine

    purchase_order = factory.SubFactory(PurchaseOrderFactory)
    product = factory.SubFactory(SupplierProductFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 50))
    quantity_received = 0
    complete = False
    closed = False
    value = factory.LazyAttribute(lambda obj: obj.product.cost * obj.quantity)


class BillOfMaterialsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BillOfMaterials

    product = factory.SubFactory(ProductFactory)


class BOMItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BOMItem

    bom = factory.SubFactory(BillOfMaterialsFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 5))


class ProductionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Production

    product = factory.SubFactory(ProductFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 100))
    quantity_received = 0
    complete = False
    closed = False
    bom_allocated = False
    bom_allocated_amount = None
    created_at = factory.LazyFunction(timezone.now)
