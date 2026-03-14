import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from main.mixins import AddressMixin


class CompanyConfig(AddressMixin, models.Model):
    """Singleton — only one row is ever allowed."""

    name = models.CharField(max_length=256)
    phone = models.CharField(max_length=64, blank=True)
    email = models.CharField(max_length=128, blank=True)
    website = models.CharField(max_length=256, blank=True)
    logo = models.ImageField(upload_to="company/", blank=True, null=True)
    vat_number = models.CharField(max_length=64, blank=True)
    company_number = models.CharField(max_length=64, blank=True)
    email_notifications = models.BooleanField(
        default=False,
        help_text="Send email copies of low-stock alerts and overdue order warnings.",
    )

    class Meta:
        verbose_name = "Company Configuration"

    def __str__(self):
        return self.name or "Company Configuration"

    def save(self, *args, **kwargs):
        if not self.pk and CompanyConfig.objects.exists():
            raise ValueError(
                "Only one CompanyConfig instance is allowed. "
                "Update the existing record instead."
            )
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Prevent deletion via ORM
        pass

    @classmethod
    def get(cls):
        """Return the singleton instance, or None if not yet configured."""
        return cls.objects.filter(pk=1).first()

    @classmethod
    def get_or_default(cls):
        """Return the singleton, falling back to an unsaved default instance."""
        instance = cls.objects.filter(pk=1).first()
        if instance is None:
            instance = cls(name="ERPv")
        return instance


class PairedInstance(models.Model):
    """A remote ERPv instance paired with this one for data exchange."""

    name = models.CharField(max_length=255)
    url = models.URLField(
        help_text="Base URL of the remote instance, e.g. https://acme.example.com"
    )
    api_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="The key they gave us to authenticate our requests",
    )
    our_key = models.CharField(
        max_length=64, blank=True, help_text="The key we generated for them to call us"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    supplier = models.ForeignKey(
        "procurement.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paired_instances",
    )
    customer = models.ForeignKey(
        "sales.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paired_instances",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.our_key:
            self.our_key = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def our_key_preview(self):
        return self.our_key[:8] + "…" if self.our_key else ""

    @property
    def status(self):
        return "active" if self.api_key else "pending"


class Notification(models.Model):
    """In-app notification for a user."""

    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        DANGER = "danger", "Danger"

    class Category(models.TextChoices):
        LOW_STOCK = "low_stock", "Low Stock"
        ORDER_OVERDUE = "order_overdue", "Order Overdue"
        ORDER_STATUS = "order_status", "Order Status Change"
        PRICE_UPDATE = "price_update", "Price Update"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=256)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=512, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title


class WebhookEndpoint(models.Model):
    """External HTTP endpoint that receives event notifications."""

    class EventType(models.TextChoices):
        ORDER_CREATED = "order.created", "Sales Order Created"
        ORDER_COMPLETED = "order.completed", "Sales Order Completed"
        SHIPMENT_COMPLETED = "shipment.completed", "Shipment Completed"
        PURCHASE_ORDER_RECEIVED = "purchase_order.received", "Purchase Order Received"
        STOCK_ADJUSTED = "stock.adjusted", "Stock Adjusted"
        PRODUCTION_COMPLETED = "production.completed", "Production Completed"

    name = models.CharField(max_length=255)
    url = models.URLField(help_text="The URL that will receive POST requests.")
    secret = models.CharField(
        max_length=128,
        blank=True,
        help_text="Shared secret for HMAC-SHA256 signature verification.",
    )
    events = models.JSONField(
        default=list, help_text="List of event types this endpoint subscribes to."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def secret_preview(self):
        return self.secret[:8] + "…" if self.secret else ""


class WebhookDelivery(models.Model):
    """Log entry for a webhook delivery attempt."""

    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Webhook deliveries"
        indexes = [
            models.Index(fields=["endpoint", "-created_at"]),
        ]

    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.event_type} → {self.endpoint.name}"
