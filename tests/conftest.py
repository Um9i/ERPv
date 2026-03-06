import pytest
from inventory.models import Product, Inventory
from production.models import BillOfMaterials, BOMItem
from procurement.models import (
    Supplier,
    SupplierContact,
    SupplierProduct,
    PurchaseOrder,
    PurchaseOrderLine,
)
from sales.models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
)


@pytest.fixture
def product(db):
    return Product.objects.create(name="product")


@pytest.fixture
def bom(db, product):
    product_2 = Product.objects.create(name="product 2")
    product_3 = Product.objects.create(name="product 3")
    bom = BillOfMaterials.objects.create(product=product)
    BOMItem.objects.create(bom=bom, product=product_2, quantity=10)
    BOMItem.objects.create(bom=bom, product=product_3, quantity=5)
    Inventory.objects.update_or_create(product=product, defaults={"quantity": 100})
    Inventory.objects.update_or_create(product=product_2, defaults={"quantity": 100})
    Inventory.objects.update_or_create(product=product_3, defaults={"quantity": 100})
    return bom


@pytest.fixture
def bom_item(db, product, bom):
    # create a separate component product so the BOM is not self-referential
    comp = Product.objects.create(name=f"component for {product.name}")
    # ensure inventory exists for the component as well
    Inventory.objects.update_or_create(product=comp, defaults={"quantity": 100})
    return BOMItem.objects.create(bom=bom, product=comp, quantity=10)


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(name="Test Supplier")


@pytest.fixture
def supplier_contact(db, supplier):
    return SupplierContact.objects.create(supplier=supplier, name="Test Contact")


@pytest.fixture
def supplier_product(db, supplier, product):
    return SupplierProduct.objects.create(
        supplier=supplier, product=product, cost=10.00
    )


@pytest.fixture
def purchase_order(db, supplier):
    return PurchaseOrder.objects.create(supplier=supplier)


@pytest.fixture
def purchase_order_line(db, purchase_order, supplier_product):
    return PurchaseOrderLine.objects.create(
        purchase_order=purchase_order,
        product=supplier_product,
        quantity=5,
        complete=False,
    )


@pytest.fixture
def customer(db):
    return Customer.objects.create(name="Test Customer")


@pytest.fixture
def customer_contact(db, customer):
    return CustomerContact.objects.create(customer=customer, name="Test Contact")


@pytest.fixture
def customer_product(db, customer, product):
    return CustomerProduct.objects.create(
        customer=customer, product=product, price=10.00
    )


@pytest.fixture
def sales_order(db, customer):
    return SalesOrder.objects.create(customer=customer)


@pytest.fixture
def sales_order_line(db, sales_order, customer_product):
    # ensure there is stock available for the product so shipping/closing
    # operations pass validation.
    inv, _ = Inventory.objects.update_or_create(
        product=customer_product.product,
        defaults={"quantity": 100},
    )
    return SalesOrderLine.objects.create(
        sales_order=sales_order, product=customer_product, quantity=5, complete=False
    )


@pytest.fixture
def sales_order_line_complete(db, sales_order_line):
    inventory_obj = Inventory.objects.get(product=sales_order_line.product.product)
    inventory_obj.quantity = 5
    inventory_obj.save()
    sol = SalesOrderLine.objects.get(pk=sales_order_line.pk)
    # simulate order fully shipped/closed
    sol.quantity_shipped = sol.quantity
    sol.complete = True
    sol.save()
    return sol


@pytest.fixture
def production_job(db, product):
    # create simple production job without BOM
    return Production.objects.create(product=product, quantity=5)
