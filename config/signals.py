"""Signal handlers that generate in-app notifications on status changes."""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Notification, WebhookEndpoint
from .webhooks import dispatch_event

User = get_user_model()


def _notify_all_users(*, category, level, title, message, link):
    """Create a notification for every active user (skipping duplicates)."""
    already_notified = set(
        Notification.objects.filter(title=title, is_read=False).values_list(
            "user_id", flat=True
        )
    )
    users = User.objects.filter(is_active=True).exclude(pk__in=already_notified)
    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                category=category,
                level=level,
                title=title,
                message=message,
                link=link,
            )
            for user in users
        ]
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
        dispatch_event(
            WebhookEndpoint.EventType.PURCHASE_ORDER_RECEIVED,
            {
                "order_id": po.pk,
                "order_number": po.order_number,
                "supplier": po.supplier.name,
                "product": product_name,
                "quantity": instance.quantity,
            },
        )


# ── Webhook-only signal handlers ────────────────────────────────────


@receiver(post_save, sender="sales.SalesOrder")
def _webhook_order_created(sender, instance, created, **kwargs):
    """Fire order.created when a new sales order is saved."""
    if not created:
        return
    dispatch_event(
        WebhookEndpoint.EventType.ORDER_CREATED,
        {
            "order_id": instance.pk,
            "order_number": instance.order_number,
            "customer": instance.customer.name,
            "ship_by_date": instance.ship_by_date,
            "total_amount": instance.total_amount,
        },
    )


@receiver(pre_save, sender="sales.SalesOrderLine")
def _webhook_shipment_completed(sender, instance, **kwargs):
    """Fire shipment.completed when a sales order line is marked complete."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if not old.complete and instance.complete:
        so = instance.sales_order
        dispatch_event(
            WebhookEndpoint.EventType.SHIPMENT_COMPLETED,
            {
                "order_id": so.pk,
                "order_number": so.order_number,
                "customer": so.customer.name,
                "product": instance.product.product.name,
                "quantity_shipped": instance.quantity_shipped,
                "quantity_ordered": instance.quantity,
            },
        )
        # Check if the entire order is now complete (all lines complete).
        other_open = (
            so.sales_order_lines.filter(complete=False).exclude(pk=instance.pk).exists()
        )
        if not other_open:
            dispatch_event(
                WebhookEndpoint.EventType.ORDER_COMPLETED,
                {
                    "order_id": so.pk,
                    "order_number": so.order_number,
                    "customer": so.customer.name,
                    "total_amount": so.total_amount,
                },
            )


@receiver(post_save, sender="inventory.InventoryAdjust")
def _webhook_stock_adjusted(sender, instance, created, **kwargs):
    """Fire stock.adjusted when a manual inventory adjustment is saved."""
    if not created:
        return
    dispatch_event(
        WebhookEndpoint.EventType.STOCK_ADJUSTED,
        {
            "product": instance.product.name,
            "product_id": instance.product_id,
            "quantity_change": instance.quantity,
        },
    )


@receiver(pre_save, sender="production.Production")
def _webhook_production_completed(sender, instance, **kwargs):
    """Fire production.completed when a production job transitions to complete."""
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    if not old.complete and instance.complete:
        dispatch_event(
            WebhookEndpoint.EventType.PRODUCTION_COMPLETED,
            {
                "job_id": instance.pk,
                "product": instance.product.name,
                "product_id": instance.product_id,
                "quantity": instance.quantity,
            },
        )
