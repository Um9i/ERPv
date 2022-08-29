import pytest
from inventory.models import Product


@pytest.fixture
def product(scope="class"):
    product = Product.objects.create(name="product 1")
    return product
