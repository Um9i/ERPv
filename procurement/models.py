from django.db import models, transaction
from inventory.models import Product, Inventory, InventoryLedger


class Supplier(models.Model):
    name = models.CharField(max_length=256, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Supplier Management"


class SupplierContact(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_contacts"
    )
    name = models.CharField(max_length=128)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Supplier Contacts"

    def __str__(self):
        return self.name


class SupplierProduct(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_products"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_suppliers"
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["product__name"]

    def __str__(self) -> str:
        return self.product.name

    def on_purchase_order(self):
        try:
            orders = sum(
                [
                    order.quantity
                    for order in self.product_purchase_orders.filter(complete=False)
                ]
            )
            return orders
        except:
            pass


class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_purchase_orders"
    )

    class Meta:
        ordering = ["-pk"]
        verbose_name_plural = "Purchase Orders"

    def __str__(self):
        return f"{self.pk}"


class PurchaseLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_ledger"
    )
    quantity = models.BigIntegerField()
    supplier = models.CharField(max_length=256)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Purchase Ledger"


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="purchase_order_lines"
    )
    product = models.ForeignKey(
        SupplierProduct,
        on_delete=models.CASCADE,
        related_name="product_purchase_orders",
    )
    quantity = models.PositiveBigIntegerField()
    complete = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        ordering = ["product"]

    def __str__(self):
        return self.product.product.name

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.complete == True and self.closed == False:
            product = Inventory.objects.select_for_update().get(
                product=self.product.product
            )
            product.quantity = product.quantity + self.quantity
            self.value = self.product.cost * self.quantity
            product.save()
            InventoryLedger.objects.create(
                product=self.product.product,
                quantity=self.quantity,
                action="Purchase Order",
                transaction_id=self.purchase_order.pk,
            )
            PurchaseLedger.objects.create(
                product=self.product.product,
                quantity=self.quantity,
                supplier=self.purchase_order.supplier,
                value=self.product.cost * self.quantity,
                transaction_id=self.purchase_order.pk,
            )
            self.closed = True
        super().save(*args, **kwargs)
