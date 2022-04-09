from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class Product(models.Model):
    name = models.CharField(max_length=256, unique=True)

    def __str__(self) -> str:
        return self.name

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

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["product"]
        verbose_name_plural = "Inventory Items"


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


class InventoryAdjust(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_adjustment"
    )
    quantity = models.BigIntegerField()
    complete = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)

    def __str__(self):
        return self.product.name

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "Inventory Adjustment"
        verbose_name = "inventory adjustment"

    def clean(self):
        if self.complete == True and self.closed == False:
            product = Inventory.objects.select_for_update().get(product=self.product)
            if product.quantity + self.quantity < 0:
                raise ValidationError(
                    _("Not enough resources to complete transaction.")
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.complete == True and self.closed == False:
            product = Inventory.objects.select_for_update().get(product=self.product)
            product.quantity = product.quantity + self.quantity
            product.save()
            InventoryLedger.objects.create(
                product=self.product,
                quantity=self.quantity,
                action="Inventory Adjustment",
                transaction_id=self.product.pk,
            )
            self.closed = True
        super().save(*args, **kwargs)
