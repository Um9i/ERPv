import json
from decimal import Decimal

from django.db import models


class FinanceDashboardSnapshot(models.Model):
    """Singleton cache row holding precomputed finance dashboard aggregates.

    Refreshed on ledger writes and inventory changes so the dashboard view
    can read directly without running expensive aggregate queries.
    """

    sales_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    purchase_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    month_sales_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    month_purchase_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    # Year and month the monthly totals refer to (enables stale-month detection)
    month_year = models.PositiveSmallIntegerField(default=0)
    month_month = models.PositiveSmallIntegerField(default=0)

    stock_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    chart_data_json = models.TextField(default="{}")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "finance dashboard snapshot"
        verbose_name_plural = "finance dashboard snapshots"

    def __str__(self) -> str:
        return f"Dashboard snapshot (updated {self.updated_at})"

    @property
    def chart_data(self) -> dict:
        return json.loads(self.chart_data_json)

    @chart_data.setter
    def chart_data(self, value: dict) -> None:
        self.chart_data_json = json.dumps(value)

    @classmethod
    def load(cls) -> "FinanceDashboardSnapshot":
        """Return the singleton row, creating it if necessary."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
