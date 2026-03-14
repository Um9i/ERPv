import pytest

from inventory.models import Inventory, Product, ProductionAllocated
from procurement.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierContact,
    SupplierProduct,
)
from production.models import BillOfMaterials, BOMItem, Production
from sales.models import (
    Customer,
    CustomerContact,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
)

_FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """Use MD5 instead of PBKDF2 so create_user() is near-instant."""
    settings.PASSWORD_HASHERS = _FAST_HASHERS


def _create_product_with_deps(name, quantity=0):
    """Create a Product + its Inventory & ProductionAllocated via bulk_create
    (bypasses post_save signals for speed)."""
    p = Product.objects.bulk_create([Product(name=name)])[0]
    Inventory.objects.bulk_create([Inventory(product=p, quantity=quantity)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


@pytest.fixture
def product(db):
    return _create_product_with_deps("product")


@pytest.fixture
def bom(db, product):
    # bulk-create component products bypassing signals
    comps = Product.objects.bulk_create(
        [Product(name="product 2"), Product(name="product 3")]
    )
    Inventory.objects.bulk_create([Inventory(product=p, quantity=100) for p in comps])
    ProductionAllocated.objects.bulk_create(
        [ProductionAllocated(product=p) for p in comps]
    )
    # components need a supplier to be valid BOM items
    sup = Supplier.objects.create(name="bom fixture supplier")
    SupplierProduct.objects.bulk_create(
        [SupplierProduct(supplier=sup, product=p, cost=1) for p in comps]
    )
    # set the main product's inventory to 100 too
    Inventory.objects.filter(product=product).update(quantity=100)
    bom = BillOfMaterials.objects.create(product=product)
    BOMItem.objects.bulk_create(
        [
            BOMItem(bom=bom, product=comps[0], quantity=10),
            BOMItem(bom=bom, product=comps[1], quantity=5),
        ]
    )
    return bom


@pytest.fixture
def bom_item(db, product, bom):
    comp = _create_product_with_deps(f"component for {product.name}", quantity=100)
    sup, _ = Supplier.objects.get_or_create(name="bom fixture supplier")
    SupplierProduct.objects.create(supplier=sup, product=comp, cost=1)
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


@pytest.fixture
def location(db):
    from inventory.models import Location

    return Location.objects.create(name="Bin A1")
