import logging

import httpx

from .models import CompanyConfig

logger = logging.getLogger(__name__)


def _notify_remote_customer(paired_instance) -> bool:
    """Tell the remote instance to create/link us as a Customer.

    Returns True on success, False on any failure (fire-and-forget).
    """
    company = CompanyConfig.get_or_default()
    payload = {
        "name": company.name,
        "address_line_1": company.address_line_1,
        "address_line_2": company.address_line_2,
        "city": company.city,
        "state": company.state,
        "postal_code": company.postal_code,
        "country": company.country,
        "phone": company.phone,
        "email": company.email,
        "website": company.website,
    }
    try:
        resp = httpx.post(
            f"{paired_instance.url.rstrip('/')}/config/api/notify/customer/",
            json=payload,
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning(
            "notify_remote_customer_failed", extra={"url": paired_instance.url}
        )
        return False


def _notify_remote_customer_product(paired_instance, product_name, price) -> bool:
    """Tell the remote instance to create/link us as a CustomerProduct.

    Returns True on success, False on any failure (fire-and-forget).
    """
    try:
        resp = httpx.post(
            f"{paired_instance.url.rstrip('/')}/config/api/notify/customer-product/",
            json={"product_name": product_name, "price": str(price)},
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning(
            "notify_remote_customer_product_failed",
            extra={"url": paired_instance.url, "product": product_name},
        )
        return False


def _notify_remote_supplier_product_cost(paired_instance, product_name, cost) -> bool:
    """Tell the remote instance to update the cost of a SupplierProduct.

    Returns True on success, False on any failure (fire-and-forget).
    """
    try:
        resp = httpx.post(
            f"{paired_instance.url.rstrip('/')}/procurement/api/notify/supplier-product/",
            json={"product_name": product_name, "cost": str(cost)},
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning(
            "notify_remote_supplier_product_cost_failed",
            extra={"url": paired_instance.url, "product": product_name},
        )
        return False


def _notify_remote_purchase_order(paired_instance, purchase_order) -> bool:
    """Tell the remote supplier instance to auto-create a matching sales order.

    Sends the PO details (due date and line items) so the supplier can
    create a corresponding SalesOrder on their side.

    Returns True on success, False on any failure (fire-and-forget).
    """
    lines = []
    for line in purchase_order.purchase_order_lines.select_related("product__product"):
        lines.append(
            {
                "product_name": line.product.product.name,
                "quantity": line.quantity,
            }
        )

    payload = {
        "order_number": purchase_order.order_number,
        "due_date": (
            purchase_order.due_date.isoformat() if purchase_order.due_date else None
        ),
        "lines": lines,
    }
    try:
        resp = httpx.post(
            f"{paired_instance.url.rstrip('/')}/sales/api/notify/purchase-order/",
            json=payload,
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        logger.warning(
            "notify_remote_purchase_order_failed",
            extra={
                "url": paired_instance.url,
                "order": purchase_order.order_number,
            },
        )
        return False
