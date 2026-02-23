from django.db import models, transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from inventory.models import Product, Inventory, InventoryLedger, ProductionAllocated


class BillOfMaterials(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)

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

    def clean(self):
        # Don't allow a products bill of materials to contain itself.
        if self.bom.product == self.product:
            raise ValidationError(_("BOM inceptions are not advisable."))


class Production(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_jobs"
    )
    quantity = models.PositiveBigIntegerField()
    # how many units of the finished product have actually been received
    quantity_received = models.PositiveBigIntegerField(default=0)
    complete = models.BooleanField(default=False)
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

    def __str__(self):
        return self.product.name

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

    def clean(self):
        if self.bom() == None:
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
    def save(self, *args, **kwargs):
        # run validation when allocating or if any quantity_received change
        should_validate = (
            (self.bom() is not None and self.bom_allocated == False)
            or (self.quantity_received > 0 and self.closed == False)
        )
        if should_validate:
            self.full_clean()

        # handle allocation
        if self.bom() is not None and self.bom_allocated == False:
            for item in self.bom():
                # accumulate across jobs rather than overwriting existing
                product = ProductionAllocated.objects.select_for_update().get(
                    product=item.product
                )
                product.quantity = (product.quantity or 0) + item.quantity * self.quantity
                product.save()
            self.bom_allocated = True
            self.bom_allocated_amount = self.quantity

        # adjust inventory for newly received amount
        prev_received = 0
        if self.pk:
            try:
                prev_received = Production.objects.get(pk=self.pk).quantity_received
            except Production.DoesNotExist:
                prev_received = 0
        delta = self.quantity_received - prev_received
        if delta > 0:
            # before making any changes ensure all components have enough stock
            if self.bom() is not None:
                for item in self.bom():
                    inv = Inventory.objects.select_for_update().get(product=item.product)
                    if inv.quantity - item.quantity * delta < 0:
                        raise ValidationError(
                            _("Not enough Inventory to complete production.")
                        )
            # increase finished product
            prod_obj = Inventory.objects.select_for_update().get(product=self.product)
            prod_obj.quantity = prod_obj.quantity + delta
            prod_obj.save()

            if self.bom() is not None:
                for item in self.bom():
                    qty_change = item.quantity * delta
                    # decrement component inventory atomically
                    Inventory.objects.select_for_update().filter(product=item.product).update(
                        quantity=F('quantity') - qty_change
                    )
                    # reduce the allocated amount atomically
                    ProductionAllocated.objects.select_for_update().filter(product=item.product).update(
                        quantity=F('quantity') - qty_change
                    )
                    InventoryLedger.objects.create(
                        product=item.product,
                        quantity=-abs(qty_change),
                        action="Production",
                        transaction_id=self.pk,
                    )
                InventoryLedger.objects.create(
                    product=self.product,
                    quantity=delta,
                    action="Production",
                    transaction_id=self.pk,
                )
            # close if we've now received everything
            if self.quantity_received >= self.quantity:
                self.closed = True
                self.complete = True

        super().save(*args, **kwargs)
