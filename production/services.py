from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Sum, F

from production.models import BillOfMaterials, Production


def bom_product_ids(product_ids: Iterable[int]) -> set[int]:
    return set(
        BillOfMaterials.objects
        .filter(product_id__in=product_ids)
        .values_list("product_id", flat=True)
    )


def pending_jobs_by_product(product_ids: Iterable[int]) -> dict[int, int]:
    job_vals = (
        Production.objects
        .filter(product_id__in=product_ids, closed=False)
        .annotate(rem=F("quantity") - F("quantity_received"))
        .values("product_id")
        .annotate(total=Sum("rem"))
    )
    return {row["product_id"]: int(row["total"] or 0) for row in job_vals}
