"""Business logic extracted from config views — pairing, import, and upsert operations."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from config.models import PairedInstance

logger = logging.getLogger(__name__)


def fetch_remote_company_data(
    instance: PairedInstance,
) -> tuple[dict[str, Any], str] | None:
    """Fetch company data from a paired remote instance.

    Returns ``(data, remote_name)`` on success, or ``None`` on HTTP/network error.
    The caller is responsible for showing error messages.
    """
    try:
        resp = httpx.get(
            f"{instance.url.rstrip('/')}/config/api/company/",
            headers={"Authorization": f"Bearer {instance.api_key}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning(
            "fetch_remote_company_data failed for %s: %s", instance.name, exc
        )
        return None
    return data, data.get("name", "").strip()


def import_catalogue_product(
    instance: PairedInstance,
    name: str,
    description: str,
    sale_price_raw: str,
    supplier_id_raw: str,
) -> tuple[bool, str]:
    """Create or update a Product + SupplierProduct from a remote catalogue item.

    Returns ``(success, message)`` so the view can set the appropriate flash level.
    Raises nothing — all errors are returned as ``(False, error_message)``.
    """
    from inventory.models import Product
    from procurement.models import Supplier, SupplierProduct

    if not name or not supplier_id_raw:
        return False, "Missing required fields (name or supplier_id)."

    try:
        cost = Decimal(sale_price_raw)
    except InvalidOperation:
        return False, f"Invalid sale price: {sale_price_raw!r}"

    try:
        supplier = Supplier.objects.get(pk=int(supplier_id_raw))
    except (Supplier.DoesNotExist, ValueError):
        return False, f"Supplier with id {supplier_id_raw!r} not found."

    existing = Product.objects.filter(name__iexact=name).first()
    product = existing or Product.objects.create(
        name=name,
        description=description,
        sale_price=cost,
        catalogue_item=False,
    )

    supplier_product, created = SupplierProduct.objects.get_or_create(
        supplier=supplier,
        product=product,
        defaults={"cost": cost},
    )
    if not created:
        supplier_product.cost = cost
        supplier_product.save(update_fields=["cost"])

    return True, f"Imported {product.name} as supplier product for {supplier.name}."


def upsert_customer_from_remote(
    paired_instance: PairedInstance,
    data: dict[str, Any],
) -> tuple[Any, bool]:
    """Create or retrieve a Customer from inbound paired-instance notification data.

    Links the customer to the paired instance and returns ``(customer, created)``.
    """
    from sales.models import Customer

    name = data.get("name", "").strip()
    existing = Customer.objects.filter(name__iexact=name).first()
    if existing:
        customer = existing
        created = False
    else:
        customer = Customer.objects.create(
            name=name,
            address_line_1=data.get("address_line_1", ""),
            address_line_2=data.get("address_line_2", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            postal_code=data.get("postal_code", ""),
            country=data.get("country", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            website=data.get("website", ""),
        )
        created = True

    paired_instance.customer = customer
    paired_instance.save(update_fields=["customer"])
    return customer, created
