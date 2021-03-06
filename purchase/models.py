from decimal import Decimal, ROUND_HALF_UP
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from inventory.models import Product
from ledger.models import PurchaseLedger, InventoryLedger


class Supplier(models.Model):
    name = models.CharField(max_length=128)
    address = models.TextField()
    postcode = models.CharField(max_length=7)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("supplier_detail", args=[str(self.id)])


class SupplierContact(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_contacts"
    )
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class PurchasedProduct(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_products"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_purchased_product"
    )
    name = models.CharField(max_length=128)
    cost = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def on_order(self):
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
    due_by = models.DateTimeField(blank=True, null=True)
    received_on = models.DateTimeField(blank=True, null=True)
    complete = models.BooleanField(default=False)

    class Meta:
        ordering = ["due_by"]

    def __str__(self):
        return f"{self.pk}"

    def value(self):
        return sum([line.value for line in self.purchase_order_lines.all()])

    def received_value(self):
        return sum([line.received_value() for line in self.purchase_order_lines.all()])

    def save(self, *args, **kwargs):
        if self.complete == True:
            PurchaseLedger.objects.create(
                name=self.pk, amount=Decimal(0.00), value=self.received_value()
            )
        super().save(*args, **kwargs)


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="purchase_order_lines"
    )
    product = models.ForeignKey(
        PurchasedProduct,
        on_delete=models.CASCADE,
        related_name="product_purchase_orders",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    received_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    created_date = models.DateTimeField(default=timezone.now)
    complete = models.BooleanField(default=False)
    complete_date = models.DateTimeField(blank=True, null=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        ordering = ["product__name"]

    @transaction.atomic
    def save(self, *args, **kwargs):
        # set the value of the line if not set.
        if self.value != Decimal(0.00):
            pass
        else:
            self.value = self.valued()
        # if line is complete add the product to inventory.
        if self.complete == True:
            product = Product.objects.select_for_update().get(
                pk=self.product.product.pk
            )
            product.quantity = product.quantity + Decimal(self.received_quantity)
            product.save()
            self.complete_date = timezone.now()
            # also create a ledger entry when receiving product
            if self.received_quantity != Decimal(0.00):
                InventoryLedger.objects.create(
                    name=self.product.product,
                    amount=self.received_quantity,
                    value=self.received_value(),
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.product.name

    def valued(self):
        try:
            v = Decimal(self.product.cost) * Decimal(self.quantity)
        except:
            v = Decimal(0.00)
        return v

    def received_value(self):
        try:
            rv = (
                Decimal(self.value)
                / Decimal(self.quantity)
                * Decimal(self.received_quantity)
            )
        except:
            rv = Decimal(0.00)
        return Decimal(rv).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
