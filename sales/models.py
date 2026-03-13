from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Sum
from django.db.models.functions import Greatest, Lower
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from inventory.models import (
    Inventory,
    InventoryLocation,
    Location,
    Product,
)
from main.mixins import AddressMixin, AuditMixin


class Customer(AddressMixin, models.Model):
    name = models.CharField(max_length=256, unique=True)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Customer Management"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="customer_name_ci_unique"),
        ]


class CustomerContact(AddressMixin, models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="customer_contacts"
    )
    name = models.CharField(max_length=128)
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
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.product.name}"

    def on_sales_order(self):
        from django.db.models import F

        total = (
            self.product_sales_orders.filter(complete=False)
            .annotate(remaining=F("quantity") - F("quantity_shipped"))
            .aggregate(total=Sum("remaining"))
            .get("total")
        )
        return max(total or 0, 0)


class SalesOrder(AuditMixin, models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="customer_sales_orders"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    ship_by_date = models.DateField(null=True, blank=True)
    total_amount_cached = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), editable=False
    )

    class Meta:
        ordering = ["-pk"]
        verbose_name_plural = "Sales Orders"
        indexes = [
            models.Index(fields=["customer"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["ship_by_date"]),
        ]

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
        from django.db.models import F

        if (
            self.sales_order_lines.filter(complete=False)
            .exclude(quantity_shipped__gte=F("quantity"))
            .exists()
        ):
            return "Open"
        return "Closed"

    @property
    def total_amount(self):
        if (
            self.total_amount_cached is not None
            and self.total_amount_cached != Decimal("0.00")
        ):
            return self.total_amount_cached
        total = self.sales_order_lines.aggregate(
            total=Sum(F("product__price") * F("quantity"))
        ).get("total")
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def remaining_total(self):
        total = self.sales_order_lines.aggregate(
            total=Sum(
                F("product__price") * Greatest(F("quantity") - F("quantity_shipped"), 0)
            )
        )["total"]
        if total is None:
            return Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def update_cached_total(self):
        total = self.sales_order_lines.aggregate(
            total=Sum(F("product__price") * F("quantity"))
        ).get("total")
        if total is None:
            total = Decimal("0.00")
        self.total_amount_cached = Decimal(total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.save(update_fields=["total_amount_cached"])


class SalesLedger(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="sales_ledger"
    )
    quantity = models.BigIntegerField()
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="sales_ledgers"
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f"{self.product}"

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Sales Ledger"
        indexes = [
            models.Index(fields=["product", "customer"]),
            models.Index(fields=["date"]),
        ]


# signal helpers to maintain cached total on the sales order header
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
        indexes = [
            models.Index(fields=["sales_order", "complete"]),
            models.Index(fields=["product"]),
            models.Index(fields=["closed"]),
        ]

    def clean(self):
        if self.complete and not self.closed:
            product = Inventory.objects.get(product=self.product.product)
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
        if self.complete and not self.closed:
            from sales.services import complete_sales_line

            complete_sales_line(self)
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


# signal handlers for cached totals
@receiver(post_save, sender=SalesOrderLine)
@receiver(post_delete, sender=SalesOrderLine)
def _update_so_cache(sender, instance, **kwargs):
    try:
        instance.sales_order.update_cached_total()
    except Exception:
        pass


class PickList(models.Model):
    """A pick list generated from a sales order to guide warehouse staff."""

    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name="pick_lists"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Pick Lists"

    def __str__(self):
        return f"Pick List for {self.sales_order.order_number}"

    @property
    def all_confirmed(self):
        """Return True if every non-shortage line has been confirmed."""
        return not self.lines.filter(is_shortage=False, confirmed=False).exists()

    def refresh(self):
        """Delete existing lines and regenerate from current stock levels."""
        self.lines.all().delete()
        self._populate_lines()

    def refresh_unconfirmed(self):
        """Re-check stock for unconfirmed lines, preserving confirmed ones."""
        self.lines.filter(confirmed=False).delete()
        confirmed_by_sol = (
            self.lines.filter(confirmed=True)
            .values("sales_order_line_id")
            .annotate(confirmed_qty=Sum("quantity"))
        )
        confirmed_map = {
            row["sales_order_line_id"]: row["confirmed_qty"] for row in confirmed_by_sol
        }
        for line in self.sales_order.sales_order_lines.filter(complete=False):
            already_confirmed = confirmed_map.get(line.pk, 0)
            remaining = line.remaining - already_confirmed
            if remaining <= 0:
                continue
            product = line.product.product
            try:
                inv = Inventory.objects.get(product=product)
            except Inventory.DoesNotExist:
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining,
                    is_shortage=True,
                )
                continue

            # figure out which locations are already claimed by confirmed lines
            confirmed_locs = (
                self.lines.filter(
                    sales_order_line=line, confirmed=True, location__isnull=False
                )
                .values("location_id")
                .annotate(used=Sum("quantity"))
            )
            confirmed_loc_map = {r["location_id"]: r["used"] for r in confirmed_locs}

            stock_locs = list(
                InventoryLocation.objects.filter(
                    inventory=inv, quantity__gt=0
                ).order_by("location__name")
            )
            allocated = 0
            for sl in stock_locs:
                if allocated >= remaining:
                    break
                available = sl.quantity - confirmed_loc_map.get(sl.location_id, 0)
                if available <= 0:
                    continue
                pick_qty = min(available, remaining - allocated)
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=sl.location,
                    quantity=pick_qty,
                )
                allocated += pick_qty

            if allocated < remaining:
                loc_total = (
                    InventoryLocation.objects.filter(inventory=inv).aggregate(
                        total=Sum("quantity")
                    )["total"]
                    or 0
                )
                unallocated_qty = max(inv.quantity - loc_total, 0)
                confirmed_unallocated = (
                    self.lines.filter(
                        sales_order_line=line, confirmed=True, location__isnull=True
                    ).aggregate(used=Sum("quantity"))["used"]
                    or 0
                )
                unallocated_qty = max(unallocated_qty - confirmed_unallocated, 0)
                if unallocated_qty > 0:
                    pick_qty = min(unallocated_qty, remaining - allocated)
                    PickListLine.objects.create(
                        pick_list=self,
                        sales_order_line=line,
                        location=None,
                        quantity=pick_qty,
                    )
                    allocated += pick_qty

            if allocated < remaining:
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining - allocated,
                    is_shortage=True,
                )

    @classmethod
    def generate_for_order(cls, sales_order):
        """Create a pick list with lines showing where to pick each product."""
        pick_list = cls.objects.create(sales_order=sales_order)
        pick_list._populate_lines()
        return pick_list

    def _populate_lines(self):
        """Create pick lines based on current stock levels."""
        for line in self.sales_order.sales_order_lines.filter(complete=False):
            remaining = line.remaining
            if remaining <= 0:
                continue
            product = line.product.product
            try:
                inv = Inventory.objects.get(product=product)
            except Inventory.DoesNotExist:
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining,
                )
                continue

            # allocate from bin locations with stock
            stock_locs = list(
                InventoryLocation.objects.filter(
                    inventory=inv, quantity__gt=0
                ).order_by("location__name")
            )
            allocated = 0
            for sl in stock_locs:
                if allocated >= remaining:
                    break
                pick_qty = min(sl.quantity, remaining - allocated)
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=sl.location,
                    quantity=pick_qty,
                )
                allocated += pick_qty

            # allocate from unallocated stock (exists but not in any bin)
            if allocated < remaining:
                loc_total = (
                    InventoryLocation.objects.filter(inventory=inv).aggregate(
                        total=Sum("quantity")
                    )["total"]
                    or 0
                )
                unallocated_qty = max(inv.quantity - loc_total, 0)
                if unallocated_qty > 0:
                    pick_qty = min(unallocated_qty, remaining - allocated)
                    PickListLine.objects.create(
                        pick_list=self,
                        sales_order_line=line,
                        location=None,
                        quantity=pick_qty,
                    )
                    allocated += pick_qty

            # true shortage — not enough stock anywhere
            if allocated < remaining:
                PickListLine.objects.create(
                    pick_list=self,
                    sales_order_line=line,
                    location=None,
                    quantity=remaining - allocated,
                    is_shortage=True,
                )


class PickListLine(models.Model):
    """A single line on a pick list indicating where to pick a product."""

    pick_list = models.ForeignKey(
        PickList, on_delete=models.CASCADE, related_name="lines"
    )
    sales_order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.CASCADE, related_name="pick_list_lines"
    )
    location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pick_list_lines",
    )
    quantity = models.PositiveBigIntegerField()
    is_shortage = models.BooleanField(default=False)
    confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sales_order_line", "location"]
        verbose_name_plural = "Pick List Lines"

    def __str__(self):
        loc = self.location or "Unallocated"
        return (
            f"{self.sales_order_line.product.product.name} × {self.quantity} from {loc}"
        )
