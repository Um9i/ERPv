from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum
from django.db.models.functions import Greatest, Lower
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from inventory.models import Product
from main.mixins import AddressMixin, AuditMixin


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
        constraints = [
            models.UniqueConstraint(Lower("name"), name="supplier_name_ci_unique"),
        ]


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
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "product"],
                name="unique_supplier_product",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self) -> str:
        return self.product.name

    def clean(self):
        if self.cost is not None and self.cost < 0:
            raise ValidationError({"cost": "Cost cannot be negative."})

    def on_purchase_order(self):
        total = (
            self.product_purchase_orders.filter(complete=False)
            .aggregate(total=Sum("quantity"))
            .get("total")
        )
        return total or 0


class PurchaseOrder(AuditMixin, models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="supplier_purchase_orders"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateField(null=True, blank=True)
    # cached aggregate of line amounts to speed up listing and reports
    total_amount_cached = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), editable=False
    )

    class Meta:
        ordering = ["-pk"]
        verbose_name_plural = "Purchase Orders"
        indexes = [
            models.Index(fields=["supplier"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["due_date"]),
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
        if (
            self.total_amount_cached is not None
            and self.total_amount_cached != Decimal("0.00")
        ):
            return self.total_amount_cached
        total = self.purchase_order_lines.aggregate(
            total=Sum(F("product__cost") * F("quantity"))
        ).get("total")
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def remaining_total(self):
        """Cash value of all remaining quantity on the order."""
        total = self.purchase_order_lines.aggregate(
            total=Sum(
                F("product__cost") * Greatest(F("quantity") - F("quantity_received"), 0)
            )
        )["total"]
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def all_store_confirmed(self):
        """Return True when every line has been scanned into the store."""
        return not self.purchase_order_lines.filter(store_confirmed=False).exists()

    def update_cached_total(self):
        """Recompute and store the aggregate amount for this order."""
        total = self.purchase_order_lines.aggregate(
            total=Sum(F("product__cost") * F("quantity"))
        ).get("total")
        if total is None:
            total = Decimal("0.00")
        self.total_amount_cached = Decimal(total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.save(update_fields=["total_amount_cached"])


class PurchaseLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_ledger"
    )
    quantity = models.BigIntegerField()
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="purchase_ledgers"
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    def clean(self):
        errors = {}
        if self.value is not None and self.value < 0:
            errors["value"] = "Value cannot be negative."
        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "Quantity must be positive."
        if errors:
            raise ValidationError(errors)

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
    store_confirmed = models.BooleanField(default=False)
    store_confirmed_at = models.DateTimeField(null=True, blank=True)

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
        self.full_clean()
        super().save(*args, **kwargs)


# signals to keep order cache up-to-date
@receiver(post_save, sender=PurchaseOrderLine)
@receiver(post_delete, sender=PurchaseOrderLine)
def _update_po_cache(sender, instance, **kwargs):
    try:
        instance.purchase_order.update_cached_total()
    except Exception:
        pass
