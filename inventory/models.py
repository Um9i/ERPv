from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Min, Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    name = models.CharField(max_length=256, unique=True)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    sale_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    catalogue_item = models.BooleanField(
        default=False,
        help_text=_("List this product in the catalogue. Requires a sale price."),
    )

    def clean(self):
        if self.catalogue_item and not self.sale_price:
            raise ValidationError(
                {"catalogue_item": _("A catalogue item must have a sale price.")}
            )

    def __str__(self) -> str:
        return self.name

    @property
    def last_sale_price(self):
        from sales.models import SalesOrderLine

        last = (
            SalesOrderLine.objects.filter(product__product=self)
            .order_by("-sales_order__created_at")
            .values_list("product__price", flat=True)
            .first()
        )
        return last

    @property
    def effective_sale_price(self):
        """sale_price if set, otherwise fall back to last sold price."""
        return self.sale_price or self.last_sale_price or 0

    @property
    def unit_cost(self):
        """Return a per-unit cost for this product.

        Priority:
        1. Cheapest supplier cost if any supplier products exist.
        2. If a bill of materials exists, compute cost as sum(component_cost * quantity).
        3. Otherwise zero.
        """
        from procurement.models import SupplierProduct
        from production.models import BOMItem, BillOfMaterials
        from collections import defaultdict

        # cheapest supplier cost for this product
        first = (
            SupplierProduct.objects.filter(product=self)
            .order_by("cost")
            .values_list("cost", flat=True)
            .first()
        )
        if first is not None:
            return first

        # no supplier — try BOM cost roll-up
        if not BillOfMaterials.objects.filter(product=self).exists():
            return 0

        # collect all product IDs in the BOM tree iteratively
        all_ids = set()
        frontier = {self.pk}
        while frontier:
            all_ids |= frontier
            children = set(
                BOMItem.objects.filter(bom__product_id__in=frontier).values_list(
                    "product_id", flat=True
                )
            )
            frontier = children - all_ids

        # bulk-load all BOM edges
        children_map = defaultdict(list)
        for parent_id, child_id, qty in BOMItem.objects.filter(
            bom__product_id__in=all_ids
        ).values_list("bom__product_id", "product_id", "quantity"):
            children_map[parent_id].append((child_id, qty))

        # bulk-load cheapest supplier cost per product
        supplier_costs = dict(
            SupplierProduct.objects.filter(product_id__in=all_ids)
            .values("product_id")
            .annotate(min_cost=Min("cost"))
            .values_list("product_id", "min_cost")
        )

        # bottom-up cost computation
        costs = {pid: supplier_costs[pid] for pid in all_ids if pid in supplier_costs}
        changed = True
        while changed:
            changed = False
            for pid in all_ids:
                if pid in costs:
                    continue
                if pid not in children_map:
                    costs[pid] = 0
                    changed = True
                elif all(cid in costs for cid, _ in children_map[pid]):
                    costs[pid] = sum(qty * costs[cid] for cid, qty in children_map[pid])
                    changed = True

        return costs.get(self.pk, 0)

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
        allocated = (
            self.product.production_allocated.aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        sales_orders = sum(
            sold.on_sales_order() for sold in self.product.product_customers.all()
        )
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


class Location(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    def __str__(self):
        return self.full_path()

    def full_path(self):
        parts = []
        node = self
        while node:
            parts.append(node.name)
            node = node.parent
        return " / ".join(reversed(parts))

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Locations"


class InventoryLocation(models.Model):
    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="stock_locations"
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="stock_locations"
    )
    quantity = models.PositiveBigIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["inventory", "location"]
        ordering = ["location"]
        verbose_name_plural = "Inventory Locations"

    def __str__(self):
        return f"{self.inventory.product.name} @ {self.location}"


class InventoryLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_ledger"
    )
    quantity = models.BigIntegerField()
    date = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=128)
    transaction_id = models.PositiveBigIntegerField()
    location = models.ForeignKey(
        "Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )

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
        product = Inventory.objects.get(product=self.product)
        if product.quantity + self.quantity < 0:
            raise ValidationError(_("Not enough resources to complete transaction."))

    @transaction.atomic
    def save(self, *args, **kwargs):
        # only apply quantity changes when creating new records
        self.full_clean()
        if self.pk is None and self.complete:
            product_qs = Inventory.objects.select_for_update().filter(
                product=self.product
            )
            # also update last_updated timestamp
            from django.utils import timezone

            product_qs.update(
                quantity=F("quantity") + self.quantity, last_updated=timezone.now()
            )
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


class StockTransfer(models.Model):
    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="transfers"
    )
    from_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="transfers_out",
    )
    to_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="transfers_in",
    )
    quantity = models.PositiveBigIntegerField()
    transferred_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-transferred_at"]
        verbose_name_plural = "Stock Transfers"

    def __str__(self):
        src = self.from_location or "Unallocated"
        dest = self.to_location or "Unallocated"
        return f"{self.inventory.product.name}: {self.quantity} " f"{src} → {dest}"

    def clean(self):
        if not self.from_location_id and not self.to_location_id:
            raise ValidationError(
                _("Source and destination cannot both be unallocated.")
            )
        if (
            self.from_location_id
            and self.to_location_id
            and self.from_location_id == self.to_location_id
        ):
            raise ValidationError(_("Source and destination must be different."))
        if self.from_location_id:
            try:
                src = InventoryLocation.objects.get(
                    inventory=self.inventory, location=self.from_location
                )
            except InventoryLocation.DoesNotExist:
                raise ValidationError(_("No stock at the source location."))
            if src.quantity < self.quantity:
                raise ValidationError(
                    _(f"Only {src.quantity} available at {self.from_location}.")
                )
        else:
            # transferring from unallocated stock
            allocated = (
                InventoryLocation.objects.filter(inventory=self.inventory).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )
            unallocated = self.inventory.quantity - allocated
            if self.quantity > unallocated:
                raise ValidationError(
                    _(f"Only {unallocated} units of unallocated stock available.")
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk is None:
            # deduct from source (skip when transferring from unallocated)
            if self.from_location_id:
                src = InventoryLocation.objects.select_for_update().get(
                    inventory=self.inventory, location=self.from_location
                )
                src.quantity -= self.quantity
                src.save(update_fields=["quantity", "last_updated"])

            # add to destination (skip when transferring to unallocated)
            if self.to_location_id:
                dest, _ = InventoryLocation.objects.select_for_update().get_or_create(
                    inventory=self.inventory,
                    location=self.to_location,
                    defaults={"quantity": 0},
                )
                dest.quantity += self.quantity
                dest.save(update_fields=["quantity", "last_updated"])

            # ledger: two entries, net zero on total stock
            InventoryLedger.objects.create(
                product=self.inventory.product,
                quantity=-self.quantity,
                action="Stock Transfer",
                transaction_id=self.inventory.pk,
                location=self.from_location,
            )
            InventoryLedger.objects.create(
                product=self.inventory.product,
                quantity=self.quantity,
                action="Stock Transfer",
                transaction_id=self.inventory.pk,
                location=self.to_location,
            )
        super().save(*args, **kwargs)
