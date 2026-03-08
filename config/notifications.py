import httpx

from .models import CompanyConfig


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
        httpx.post(
            f"{paired_instance.url.rstrip('/')}/config/api/notify/customer/",
            json=payload,
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=5,
        )
        return True
    except Exception:
        return False


def _notify_remote_customer_product(paired_instance, product_name, price) -> bool:
    """Tell the remote instance to create/link us as a CustomerProduct.

    Returns True on success, False on any failure (fire-and-forget).
    """
    try:
        httpx.post(
            f"{paired_instance.url.rstrip('/')}/config/api/notify/customer-product/",
            json={"product_name": product_name, "price": str(price)},
            headers={"Authorization": f"Bearer {paired_instance.api_key}"},
            timeout=5,
        )
        return True
    except Exception:
        return False
