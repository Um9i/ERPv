from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from inventory.models import Inventory, Product, ProductionAllocated


class BillOfMaterials(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    production_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Additional per-unit cost for labour, overhead, etc.",
    )

    class Meta:
        ordering = ["product"]
        verbose_name_plural = "Bill of Materials Configuration"
        indexes = [
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return self.product.name


class BOMItem(models.Model):
    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.CASCADE, related_name="bom_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_bom_items"
    )
    quantity = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["product__name"]
        indexes = [
            models.Index(fields=["bom"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def _get_all_sub_products(self, product, visited=None):
        """Iteratively collect all sub-product IDs using bulk queries."""
        visited = set()
        frontier = {product.pk}
        while frontier:
            visited |= frontier
            children = set(
                BOMItem.objects.filter(bom__product_id__in=frontier).values_list(
                    "product_id", flat=True
                )
            )
            frontier = children - visited
        return visited

    def clean(self):
        # Don't allow a products bill of materials to contain itself.
        if self.bom.product == self.product:
            raise ValidationError(_("BOM inceptions are not advisable."))

        # Don't allow circular references: if the product being added as a
        # BOM item itself has a BOM that (directly or indirectly) contains
        # the parent product, reject it.
        sub_products = self._get_all_sub_products(self.product, visited=set())
        if self.bom.product.pk in sub_products:
            raise ValidationError(
                _(
                    "Circular BOM reference detected: %(product)s already contains "
                    "%(parent)s in its bill of materials."
                ),
                params={
                    "product": self.product.name,
                    "parent": self.bom.product.name,
                },
            )


class Production(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_jobs"
    )
    quantity = models.PositiveBigIntegerField()
    # how many units of the finished product have actually been received
    quantity_received = models.PositiveBigIntegerField(default=0)
    complete = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    closed = models.BooleanField(default=False)
    bom_allocated = models.BooleanField(default=False)
    bom_allocated_amount = models.PositiveBigIntegerField(blank=True, null=True)

    def __str__(self):
        return self.product.name

    @property
    def order_number(self):
        return f"PR{self.pk:05d}"

    @property
    def date(self):
        return self.created_at

    @property
    def remaining(self):
        return max(self.quantity - self.quantity_received, 0)

    @property
    def status(self):
        # derive a human-friendly status based on reception and closure
        if self.closed:
            return "Closed"
        if self.quantity_received > 0:
            return "Completing"
        if self.bom_allocated:
            return "Allocated"
        return "Open"

    class Meta:
        ordering = ["-closed", "-pk"]
        verbose_name_plural = "Production Planning"
        verbose_name = "planned production"
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["complete", "closed"]),
            models.Index(fields=["bom_allocated"]),
        ]

    def bom(self):
        try:
            bom = [
                item
                for item in self.product.billofmaterials.bom_items.all().prefetch_related(
                    "product"
                )
            ]
            return bom
        except AttributeError:
            return None

    @property
    def materials_available(self):
        """Return ``True`` if current inventory can cover the full job quantity.

        Previously the list view showed ``product.can_produce`` which only
        checked materials for a *single* unit; a job of quantity 40 could show
        a green check when only enough components for one unit existed.  We
        need a job‑level predicate that scales the component requirements by
        ``self.quantity``.
        """
        if self.bom() is None:
            return False
        # lazy import Inventory to avoid cycle at module import time
        from inventory.models import Inventory

        for item in self.bom():
            try:
                inv = Inventory.objects.get(product=item.product)
            except Inventory.DoesNotExist:
                return False
            if inv.quantity < item.quantity * self.quantity:
                return False
        return True

    @property
    def materials_available_for_remaining(self):
        """Return ``True`` if inventory can cover the remaining job quantity."""
        return self.max_receivable >= self.remaining

    @property
    def max_receivable(self):
        """Max units that can be received given current inventory."""
        if self.bom() is None:
            return 0
        from inventory.models import Inventory

        cap = self.remaining
        for item in self.bom():
            try:
                inv = Inventory.objects.get(product=item.product)
            except Inventory.DoesNotExist:
                return 0
            if item.quantity > 0:
                cap = min(cap, inv.quantity // item.quantity)
        return cap

    def clean(self):
        if self.bom() is None:
            raise ValidationError(_("Product has no Bill of Materials."))
        # when attempting to receive anything ensure components are available
        if self.quantity_received > 0 and self.bom() is not None:
            for item in self.bom():
                product = Inventory.objects.select_for_update().get(
                    product=item.product
                )
                if product.quantity - item.quantity * self.quantity_received < 0:
                    raise ValidationError(
                        _("Not enough Inventory to complete production.")
                    )

    @transaction.atomic
    def save(self, *args, skip_allocation=False, **kwargs):
        from production.services import allocate_production, receive_production

        # run validation when allocating or if any quantity_received change
        should_validate = (
            self.bom() is not None and not self.bom_allocated and not skip_allocation
        ) or (self.quantity_received > 0 and not self.closed)
        if should_validate:
            self.full_clean()

        # handle allocation via service
        if self.bom() is not None and not self.bom_allocated and not skip_allocation:
            allocate_production(self)

        # adjust inventory for newly received amount via service
        prev_received = 0
        if self.pk:
            try:
                prev_received = Production.objects.get(pk=self.pk).quantity_received
            except Production.DoesNotExist:
                prev_received = 0
        delta = self.quantity_received - prev_received
        affected_product_ids = receive_production(self, delta)

        super().save(*args, **kwargs)

        if affected_product_ids:
            from inventory.services import refresh_required_cache_for_products

            refresh_required_cache_for_products(affected_product_ids)

    @transaction.atomic
    def cancel(self):
        """Cancel a job and release any remaining allocated materials."""
        if self.closed:
            return

        outstanding_qty = max(
            (self.bom_allocated_amount or 0) - self.quantity_received, 0
        )
        affected_product_ids = {self.product_id}

        if self.bom() is not None and outstanding_qty > 0:
            for item in self.bom():
                qty_change = item.quantity * outstanding_qty
                alloc = ProductionAllocated.objects.select_for_update().get(
                    product=item.product
                )
                alloc.quantity = max((alloc.quantity or 0) - qty_change, 0)
                alloc.save(update_fields=["quantity"])
                affected_product_ids.add(item.product_id)

        self.bom_allocated = False
        self.bom_allocated_amount = None
        self.closed = True
        self.complete = False
        self.save(
            skip_allocation=True,
            update_fields=[
                "bom_allocated",
                "bom_allocated_amount",
                "closed",
                "complete",
                "updated_at",
            ],
        )

        if affected_product_ids:
            from inventory.services import refresh_required_cache_for_products

            refresh_required_cache_for_products(affected_product_ids)
