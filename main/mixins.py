from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models


class HtmxPartialMixin:
    """View mixin that returns a partial template for HTMX requests.

    Set ``partial_template_name`` on the view class.
    """

    partial_template_name: str = ""

    def get_template_names(self: Any) -> list[str]:
        if self.request.headers.get("HX-Request"):
            return [self.partial_template_name]
        return [self.template_name]


class AuditMixin(models.Model):
    """Abstract mixin providing created_by and updated_by audit trail fields."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        editable=False,
    )

    class Meta:
        abstract = True


class AddressMixin(models.Model):
    """Abstract mixin providing structured address fields.

    Replaces the old single ``address = TextField`` with discrete fields for
    line 1/2, city, state/region, postal code, and country.  A convenience
    property ``full_address`` concatenates non-empty parts for display.
    """

    address_line_1 = models.CharField("Address line 1", max_length=256, blank=True)
    address_line_2 = models.CharField("Address line 2", max_length=256, blank=True)
    city = models.CharField(max_length=128, blank=True)
    state = models.CharField("State / Region", max_length=128, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=128, blank=True)

    class Meta:
        abstract = True

    @property
    def full_address(self) -> str:
        """Return a single-string representation of the address."""
        parts = [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.state,
            self.postal_code,
            self.country,
        ]
        return ", ".join(p for p in parts if p)

    # Backward-compatible alias so templates using {{ obj.address }} still work
    # during the transition period.
    @property
    def address(self) -> str:  # noqa: D401
        return self.full_address
