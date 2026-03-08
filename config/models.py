import secrets

from django.db import models
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
