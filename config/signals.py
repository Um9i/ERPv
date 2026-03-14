"""Signal handlers that generate in-app notifications on status changes."""

import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Notification, WebhookEndpoint
from .webhooks import dispatch_event

User = get_user_model()

logger = logging.getLogger(__name__)


def _notify_all_users(*, category, level, title, message, link):
    """Create a notification for every active user (skipping duplicates)."""
    already_notified = set(
        Notification.objects.filter(
            title=title, message=message, is_read=False
        ).values_list("user_id", flat=True)
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
        logger.info(
            "so_line_completed",
            extra={"order": so.order_number, "product": product_name},
        )
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
        logger.info(
            "po_line_received",
            extra={"order": po.order_number, "product": product_name},
        )
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


# ── Purchase order → remote supplier ────────────────────────────────


@receiver(post_save, sender="procurement.PurchaseOrder")
def _notify_remote_supplier_purchase_order(sender, instance, created, **kwargs):
    """When a PO is created, notify the supplier's paired instance."""
    if not created:
        return
    from config.models import PairedInstance
    from config.notifications import _notify_remote_purchase_order

    paired = PairedInstance.objects.filter(
        supplier=instance.supplier, api_key__gt=""
    ).first()
    if not paired:
        return
    if not _notify_remote_purchase_order(paired, instance):
        logger.warning(
            "remote_purchase_order_notify_failed",
            extra={
                "order": instance.order_number,
                "supplier": instance.supplier.name,
            },
        )


# ── Inventory shortage notifications ────────────────────────────────


@receiver(post_save, sender="sales.SalesOrderLine")
def _notify_sales_order_shortage(sender, instance, created, **kwargs):
    """When a sales order line is created, notify if inventory is insufficient."""
    if not created:
        return

    from inventory.models import Inventory
    from production.models import BillOfMaterials

    product = instance.product.product
    try:
        inv = Inventory.objects.get(product=product)
    except Inventory.DoesNotExist:
        inv = None

    stock = inv.quantity if inv else 0
    if stock >= instance.quantity:
        return

    shortage = instance.quantity - stock
    so = instance.sales_order
    has_bom = BillOfMaterials.objects.filter(product=product).exists()

    if has_bom:
        action = "produce or procure"
        link = (
            reverse("production:production-create")
            + f"?product={product.pk}&quantity={shortage}"
        )
    else:
        action = "procure"
        link = reverse("procurement:purchase-order-list")

    _notify_all_users(
        category=Notification.Category.LOW_STOCK,
        level=Notification.Level.WARNING,
        title=f"Insufficient stock: {product.name}",
        message=(
            f"{so.order_number} requires {instance.quantity} × {product.name} "
            f"but only {stock} in stock (short {shortage}). "
            f"Consider creating a job to {action} the remaining inventory."
        ),
        link=link,
    )


@receiver(post_save, sender="production.Production")
def _notify_production_material_shortage(sender, instance, created, **kwargs):
    """When a production job is created, notify if BOM materials are insufficient."""
    if not created:
        return

    from inventory.models import Inventory
    from production.models import BillOfMaterials, BOMItem

    try:
        bom = BillOfMaterials.objects.get(product=instance.product)
    except BillOfMaterials.DoesNotExist:
        return

    bom_items = BOMItem.objects.filter(bom=bom).select_related("product")
    inv_map = {
        inv.product_id: inv.quantity
        for inv in Inventory.objects.filter(
            product__in=[item.product for item in bom_items]
        )
    }

    shortages = []
    for item in bom_items:
        required = item.quantity * instance.quantity
        available = inv_map.get(item.product_id, 0)
        if available < required:
            short = required - available
            has_sub_bom = BillOfMaterials.objects.filter(product=item.product).exists()
            shortages.append((item.product, short, has_sub_bom))

    if not shortages:
        return

    lines = []
    for product, short, has_sub_bom in shortages:
        action = "produce or procure" if has_sub_bom else "procure"
        lines.append(f"  • {product.name}: short {short} (can {action})")

    _notify_all_users(
        category=Notification.Category.LOW_STOCK,
        level=Notification.Level.WARNING,
        title=f"Material shortage: {instance.order_number}",
        message=(
            f"Production job {instance.order_number} for "
            f"{instance.quantity} × {instance.product.name} "
            f"has insufficient materials:\n" + "\n".join(lines)
        ),
        link=reverse("production:production-detail", args=[instance.pk]),
    )
