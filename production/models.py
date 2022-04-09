from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from inventory.models import Product, Inventory, InventoryLedger, ProductionAllocated


class BillOfMaterials(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)

    class Meta:
        ordering = ["product"]
        verbose_name_plural = "Bill of Materials Configuration"

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
    complete = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    bom_allocated = models.BooleanField(default=False)
    bom_allocated_amount = models.PositiveBigIntegerField(blank=True, null=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Production Planning"
        verbose_name = "planned production"

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
        except:
            pass

    def clean(self):
        if self.bom() == None:
            raise ValidationError(_("Product has no Bill of Materials."))
        if self.complete == True:
            if self.bom() is not None:
                for item in self.bom():
                    product = Inventory.objects.select_for_update().get(
                        product=item.product
                    )
                    if product.quantity - item.quantity * self.quantity < 0:
                        raise ValidationError(
                            _("Not enough Inventory to complete production.")
                        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.bom() is not None and self.bom_allocated == False:
            for item in self.bom():
                product = ProductionAllocated.objects.select_for_update().get(
                    product=item.product
                )
                product.quantity = item.quantity * self.quantity
                product.save()
            self.bom_allocated = True
            self.bom_allocated_amount = self.quantity
        if self.complete == True and self.closed == False:
            product = Inventory.objects.select_for_update().get(product=self.product)
            product.quantity = product.quantity + self.quantity
            product.save()
            if self.bom() is not None:
                for item in self.bom():
                    product = Inventory.objects.select_for_update().get(
                        product=item.product
                    )
                    product.quantity = product.quantity - item.quantity * self.quantity
                    product.save()
                    prod_allocation = (
                        ProductionAllocated.objects.select_for_update().get(
                            product=item.product
                        )
                    )
                    prod_allocation.quantity = (
                        prod_allocation.quantity
                        - item.quantity * self.bom_allocated_amount
                    )
                    prod_allocation.save()
                    InventoryLedger.objects.create(
                        product=item.product,
                        quantity=-abs(item.quantity * self.quantity),
                        action="Production",
                        transaction_id=self.pk,
                    )
                InventoryLedger.objects.create(
                    product=self.product,
                    quantity=self.quantity,
                    action="Production",
                    transaction_id=self.pk,
                )
            self.closed = True
        super().save(*args, **kwargs)
