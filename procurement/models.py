from django.db import models, transaction
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from inventory.models import Product, Inventory, InventoryLedger
from main.mixins import AddressMixin


class Supplier(AddressMixin, models.Model):
    name = models.CharField(max_length=256, unique=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Supplier Management"


class SupplierContact(AddressMixin, models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_contacts"
    )
    name = models.CharField(max_length=128)
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
        indexes = [
            models.Index(fields=["supplier"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self) -> str:
        return self.product.name

    def on_purchase_order(self):
        total = (
            self.product_purchase_orders.filter(complete=False).aggregate(total=Sum('quantity'))
            .get('total')
        )
        return total or 0

    class Meta:
        unique_together = ("supplier", "product")

class PurchaseOrder(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_purchase_orders"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    # cached aggregate of line amounts to speed up listing and reports
    total_amount_cached = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"), editable=False)

    class Meta:
        ordering = ["-pk"]
        verbose_name_plural = "Purchase Orders"
        indexes = [
            models.Index(fields=["supplier"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"PO{self.pk:05d}"  # nice padded number

    # convenience properties used in templates
    @property
    def order_number(self):
        return str(self)

    @property
    def date(self):
        return self.created_at

    @property
    def status(self):
        if self.purchase_order_lines.filter(complete=False).exists():
            return "Open"
        return "Closed"

    @property
    def total_amount(self):
        # return cached value when possible; fall back to recalculation if
        # the cache is zero (e.g., before first save) or missing.
        if self.total_amount_cached is not None and self.total_amount_cached != Decimal("0.00"):
            return self.total_amount_cached
        total = (
            self.purchase_order_lines.aggregate(
                total=Sum(F("product__cost") * F("quantity"))
            ).get("total")
        )
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def remaining_total(self):
        """Cash value of all remaining quantity on the order."""
        total = Decimal("0.00")
        for line in self.purchase_order_lines.all():
            # remaining_total on line already does the right thing
            rt = line.remaining_total
            if rt is not None:
                total += rt
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def update_cached_total(self):
        """Recompute and store the aggregate amount for this order."""
        total = (
            self.purchase_order_lines.aggregate(
                total=Sum(F("product__cost") * F("quantity"))
            ).get("total")
        )
        if total is None:
            total = Decimal("0.00")
        self.total_amount_cached = Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.save(update_fields=["total_amount_cached"])


class PurchaseLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_ledger"
    )
    quantity = models.BigIntegerField()
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchase_ledgers'
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Purchase Ledger"
        indexes = [
            models.Index(fields=["product", "supplier"]),
            models.Index(fields=["date"]),
        ]


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
    quantity_received = models.PositiveBigIntegerField(default=0)
    complete = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        ordering = ["product"]
        indexes = [
            models.Index(fields=["purchase_order", "complete"]),
            models.Index(fields=["product"]),
            models.Index(fields=["closed"]),
        ]

    def __str__(self):
        return self.product.product.name

    @property
    def unit_price(self):
        # take cost from the supplier-product relationship
        return self.product.cost

    @property
    def total_price(self):
        # if value already recorded use it, otherwise compute
        if self.value is not None:
            return self.value
        if self.unit_price is None:
            return None
        return self.unit_price * self.quantity

    @property
    def received_total(self):
        """Monetary value of what has been received so far."""
        if self.unit_price is None:
            return None
        return self.unit_price * self.quantity_received

    @property
    def remaining(self):
        """Quantity still to be received (non‑negative)."""
        return max(self.quantity - self.quantity_received, 0)

    @property
    def remaining_total(self):
        """Monetary value still outstanding on this line."""
        if self.unit_price is None:
            return None
        return self.unit_price * self.remaining

    @transaction.atomic
    def save(self, *args, **kwargs):
        # Ensure validation runs before making inventory changes
        self.full_clean()
        # when the line is being marked complete (first time) and not
        # previously closed we perform the inventory adjustment. this
        # logic still uses `self.quantity` because the order quantity is
        # what drives stock increases; the view responsible for receiving
        # will update `quantity_received` separately.
        if self.complete == True and self.closed == False:
            product_qs = Inventory.objects.select_for_update().filter(
                product=self.product.product
            )
            from django.utils import timezone
            product_qs.update(quantity=F('quantity') + self.quantity, last_updated=timezone.now())
            # record monetary value
            try:
                self.value = self.product.cost * self.quantity
            except Exception:
                self.value = None
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
                value=self.value or 0,
                transaction_id=self.purchase_order.pk,
            )
            # keep inventory shortage cache in sync when stock increases
            from inventory.services import refresh_required_cache_for_products

            refresh_required_cache_for_products([self.product.product_id])
            self.closed = True
        super().save(*args, **kwargs)


# signals to keep order cache up-to-date
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=PurchaseOrderLine)
@receiver(post_delete, sender=PurchaseOrderLine)
def _update_po_cache(sender, instance, **kwargs):
    try:
        instance.purchase_order.update_cached_total()
    except Exception:
        pass
