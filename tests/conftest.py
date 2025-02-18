import pytest
from inventory.models import Product, Inventory
from production.models import BillOfMaterials, BOMItem
from procurement.models import Supplier, SupplierContact, SupplierProduct, PurchaseOrder, PurchaseOrderLine
from inventory.models import Product, Inventory
from sales.models import Customer, CustomerContact, CustomerProduct, SalesOrder, SalesOrderLine

@pytest.fixture
def product(scope="class"):
    product = Product.objects.create(name="product")
    return product

@pytest.fixture
def bom(scope="class"):
    product = Product.objects.get(pk=1)
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
def bom_item(scope="class"):
    product = Product.objects.get(pk=1)
    bom = BillOfMaterials.objects.get(pk=1)
    bom_item = BOMItem.objects.create(bom=bom, product=product, quantity=10)
    return bom_item

@pytest.fixture
def supplier(db):
    return Supplier.objects.create(name="Test Supplier")

@pytest.fixture
def supplier_contact(db, supplier):
    return SupplierContact.objects.create(supplier=supplier, name="Test Contact")

@pytest.fixture
def supplier_product(db, supplier, product):
    return SupplierProduct.objects.create(supplier=supplier, product=product, cost=10.00)

@pytest.fixture
def purchase_order(db, supplier):
    return PurchaseOrder.objects.create(supplier=supplier)

@pytest.fixture
def purchase_order_line(db, purchase_order, supplier_product):
    return PurchaseOrderLine.objects.create(purchase_order=purchase_order, product=supplier_product, quantity=5, complete=False)

@pytest.fixture
def customer(db):
    return Customer.objects.create(name="Test Customer")

@pytest.fixture
def customer_contact(db, customer):
    return CustomerContact.objects.create(customer=customer, name="Test Contact")

@pytest.fixture
def customer_product(db, customer, product):
    return CustomerProduct.objects.create(customer=customer, product=product, price=10.00)

@pytest.fixture
def sales_order(db, customer):
    return SalesOrder.objects.create(customer=customer)

@pytest.fixture
def sales_order_line(db, sales_order, customer_product):
    return SalesOrderLine.objects.create(sales_order=sales_order, product=customer_product, quantity=5, complete=False)

@pytest.fixture
def sales_order_line_complete(db, sales_order_line):
    product = Inventory.objects.get(product=sales_order_line.product.product)
    product.quantity = 5
    product.save()
    sales_order_line_complete = SalesOrderLine.objects.get(pk=1)
    sales_order_line_complete.complete = True
    print(sales_order_line_complete.product.product.product_inventory.quantity)
    sales_order_line_complete.save()
    return sales_order_line_complete
