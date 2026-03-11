"""Signal handlers that generate in-app notifications on status changes."""

from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Notification

User = get_user_model()


def _notify_all_users(*, category, level, title, message, link):
    """Create a notification for every active user (skipping duplicates)."""
    users = User.objects.filter(is_active=True)
    for user in users:
        if Notification.objects.filter(user=user, title=title, is_read=False).exists():
            continue
        Notification.objects.create(
            user=user,
            category=category,
            level=level,
            title=title,
            message=message,
            link=link,
        )


@receiver(pre_save, sender="sales.SalesOrderLine")
def _notify_sales_order_completed(sender, instance, **kwargs):
    """When a sales order line is marked complete, notify users."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if not old.complete and instance.complete:
        so = instance.sales_order
        product_name = instance.product.product.name
        _notify_all_users(
            category=Notification.Category.ORDER_STATUS,
            level=Notification.Level.INFO,
            title=f"SO line shipped: {product_name}",
            message=f"{so.order_number} — {instance.quantity} × {product_name} completed.",
            link=reverse("sales:sales-order-detail", args=[so.pk]),
        )


@receiver(pre_save, sender="procurement.PurchaseOrderLine")
def _notify_purchase_order_received(sender, instance, **kwargs):
    """When a purchase order line is marked complete, notify users."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if not old.complete and instance.complete:
        po = instance.purchase_order
        product_name = instance.product.product.name
        _notify_all_users(
            category=Notification.Category.ORDER_STATUS,
            level=Notification.Level.INFO,
            title=f"PO line received: {product_name}",
            message=f"{po.order_number} — {instance.quantity} × {product_name} received.",
            link=reverse("procurement:purchase-order-detail", args=[po.pk]),
        )
