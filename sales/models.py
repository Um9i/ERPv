from django.db import models, transaction
from django.db.models import F, Sum
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from inventory.models import Product, Inventory, InventoryLedger


class Customer(models.Model):
    name = models.CharField(max_length=256, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Customer Management"


class CustomerContact(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="customer_contacts"
    )
    name = models.CharField(max_length=128)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Customer Contacts"

    def __str__(self):
        return self.name


class CustomerProduct(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="customer_products"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_customers"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product.name}"

    def on_sales_order(self):
        total = (
            self.product_sales_orders.filter(complete=False).aggregate(total=Sum('quantity'))
            .get('total')
        )
        return total or 0


class SalesOrder(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="customer_sales_orders"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pk"]
        verbose_name_plural = "Sales Orders"

    def __str__(self):
        # padded number similar to purchase order for nicer display
        return f"SO{self.pk:05d}"

    # convenience properties used in templates
    @property
    def order_number(self):
        return str(self)

    @property
    def date(self):
        return self.created_at

    @property
    def status(self):
        if self.sales_order_lines.filter(complete=False).exists():
            return "Open"
        return "Closed"

    @property
    def total_amount(self):
        total = (
            self.sales_order_lines.aggregate(
                total=Sum(F("product__price") * F("quantity"))
            ).get("total")
        )
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def remaining_total(self):
        total = Decimal("0.00")
        for line in self.sales_order_lines.all():
            rt = line.remaining_total
            if rt is not None:
                total += rt
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SalesLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="sales_ledger"
    )
    quantity = models.BigIntegerField()
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='sales_ledgers'
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Sales Ledger"


class SalesOrderLine(models.Model):
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name="sales_order_lines"
    )
    product = models.ForeignKey(
        CustomerProduct, on_delete=models.CASCADE, related_name="product_sales_orders"
    )
    quantity = models.PositiveBigIntegerField()
    quantity_shipped = models.PositiveBigIntegerField(default=0)
    complete = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        ordering = ["product"]

    def clean(self):
        if self.complete == True and self.closed == False:
            product = Inventory.objects.select_for_update().get(
                product=self.product.product
            )
            if product.quantity - self.quantity < 0:
                raise ValidationError(
                    _("Not enough resources to complete transaction.")
                )

    @transaction.atomic
    def save(self, *args, **kwargs):
        # run validation first
        self.full_clean()
        # only adjust inventory when the entire line is being closed for the
        # first time; partial shipments are handled by the view logic which
        # manually updates stock/ledgers and increments ``quantity_shipped``.
        if self.complete == True and self.closed == False:
            product_qs = Inventory.objects.select_for_update().filter(
                product=self.product.product
            )
            # decrement atomically
            product_qs.update(quantity=F('quantity') - self.quantity)
            try:
                self.value = self.product.price * self.quantity
            except Exception:
                self.value = None
            InventoryLedger.objects.create(
                product=self.product.product,
                quantity=-abs(self.quantity),
                action="Sales Order",
                transaction_id=self.sales_order.pk,
            )
            SalesLedger.objects.create(
                product=self.product.product,
                quantity=self.quantity,
                customer=self.sales_order.customer,
                value=self.value or 0,
                transaction_id=self.sales_order.pk,
            )
            self.closed = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.product.product.name

    # computed helpers mirroring procurement's order line
    @property
    def unit_price(self):
        return self.product.price

    @property
    def total_price(self):
        if self.value is not None:
            return self.value
        if self.unit_price is None:
            return None
        return self.unit_price * self.quantity

    @property
    def shipped_total(self):
        if self.unit_price is None:
            return None
        return self.unit_price * self.quantity_shipped

    @property
    def remaining(self):
        return max(self.quantity - self.quantity_shipped, 0)

    @property
    def remaining_total(self):
        if self.unit_price is None:
            return None
        return self.unit_price * self.remaining
