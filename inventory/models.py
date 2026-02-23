from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_save
from django.db.models import F
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    name = models.CharField(max_length=256, unique=True)

    def __str__(self) -> str:
        return self.name

    @property
    def unit_cost(self):
        """Return a per-unit cost for this product.

        Priority:
        1. Cheapest supplier cost if any supplier products exist.
        2. If a bill of materials exists, compute cost as sum(component_cost * quantity).
        3. Otherwise zero.
        """
        # cheapest supplier cost
        suppliers = self.product_suppliers.all().order_by('cost')
        if suppliers.exists():
            try:
                return suppliers.first().cost
            except Exception:
                return 0
        # compute from BOM if available
        try:
            bom = self.billofmaterials
        except Product.billofmaterials.RelatedObjectDoesNotExist:
            return 0
        total = 0
        for item in bom.bom_items.all().select_related('product'):
            # recursive call
            total += item.quantity * item.product.unit_cost
        return total

    @property
    def can_produce(self):
        """Return ``True`` if there is sufficient inventory of every component
        required for a single unit of this product's bill of materials.

        Products without a BOM are not producible.  If a BOM item refers to a
        component that has no inventory record we treat it as unavailable.
        """
        try:
            bom = self.billofmaterials
        except Product.billofmaterials.RelatedObjectDoesNotExist:
            return False
        # lazy-import to avoid circular import
        from .models import Inventory
        for item in bom.bom_items.select_related("product").all():
            try:
                inv = item.product.product_inventory
            except Inventory.DoesNotExist:
                return False
            if inv.quantity < item.quantity:
                return False
        return True

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Inventory Management"


@receiver(post_save, sender=Product)
def create_inventory(sender, instance, created, **kwargs):
    if created:
        Inventory.objects.create(product=instance)


class Inventory(models.Model):
    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name="product_inventory"
    )
    quantity = models.PositiveBigIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    # cache of ``required`` property to avoid recalculating in queries
    required_cached = models.BigIntegerField(default=0, editable=False)

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["product"]
        verbose_name_plural = "Inventory Items"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["last_updated"]),
        ]

    @property
    def required(self) -> int:
        """Quantity required to satisfy allocated production and sales orders.

        Mirrors logic previously implemented in the admin helper.  Positive
        value indicates how many more units we need (stock minus demand).
        """
        # allocated production amount
        allocated = sum(job.quantity for job in self.product.production_allocated.all())
        # sales orders demand (customer products have on_sales_order helper)
        sales_orders = sum(
            sold.on_sales_order() for sold in self.product.product_customers.all()
        )
        # compute shortage relative to current stock
        short = self.quantity - allocated - sales_orders
        return abs(short) if short < 0 else 0


    def update_required_cached(self):
        """Recompute and persist the cached required quantity."""
        self.required_cached = self.required
        self.save(update_fields=["required_cached"])


@receiver(post_save, sender=Product)
def create_production_allocation(sender, instance, created, **kwargs):
    if created:
        ProductionAllocated.objects.create(product=instance)


class ProductionAllocated(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="production_allocated"
    )
    quantity = models.PositiveBigIntegerField(blank=True, null=True, default=0)

    def __str__(self):
        return self.product.name

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Production Allocated"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["quantity"]),
        ]


class InventoryLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_ledger"
    )
    quantity = models.BigIntegerField()
    date = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=128)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Inventory Ledger"
        indexes = [
            models.Index(fields=["product", "date"]),
            models.Index(fields=["transaction_id"]),
        ]


class InventoryAdjust(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_adjustment"
    )
    quantity = models.BigIntegerField()
    # keep the field for backwards compatibility but default to True and
    # hide it from user input; adjustments are always applied immediately
    complete = models.BooleanField(default=True)

    def __str__(self):
        return self.product.name

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Inventory Adjustment"
        verbose_name = "inventory adjustment"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["complete"]),
        ]

    def clean(self):
        # validate against inventory before applying change
        product = Inventory.objects.select_for_update().get(product=self.product)
        if product.quantity + self.quantity < 0:
            raise ValidationError(
                _("Not enough resources to complete transaction.")
            )
        # no change to cached requirements here; the quantity check occurs
        # under ``select_for_update`` which will be followed by an adjustment

    @transaction.atomic
    def save(self, *args, **kwargs):
        # only apply quantity changes when creating new records
        self.full_clean()
        if self.pk is None and self.complete:
            product_qs = Inventory.objects.select_for_update().filter(product=self.product)
            # also update last_updated timestamp
            from django.utils import timezone
            product_qs.update(quantity=F('quantity') + self.quantity, last_updated=timezone.now())
            InventoryLedger.objects.create(
                product=self.product,
                quantity=self.quantity,
                action="Inventory Adjustment",
                transaction_id=self.product.pk,
            )
            # refresh cached required value for this inventory
            inv = Inventory.objects.get(product=self.product)
            inv.update_required_cached()
        super().save(*args, **kwargs)


# signal handlers to keep the required_cached field in sync
@receiver(post_save, sender=ProductionAllocated)
@receiver(post_delete, sender=ProductionAllocated)
def _update_required_from_allocation(sender, instance, **kwargs):
    try:
        inv = Inventory.objects.get(product=instance.product)
        inv.update_required_cached()
    except Inventory.DoesNotExist:
        pass


from sales.models import SalesOrderLine  # imported here to avoid circular import

@receiver(post_save, sender=SalesOrderLine)
@receiver(post_delete, sender=SalesOrderLine)
def _update_required_from_sales(sender, instance, **kwargs):
    try:
        inv = Inventory.objects.get(product=instance.product.product)
        inv.update_required_cached()
    except Inventory.DoesNotExist:
        pass
