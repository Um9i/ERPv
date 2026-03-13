"""Management command that generates in-app notifications.

Checks for:
  * Low-stock products (required_cached > 0 means demand > supply)
  * Overdue purchase orders (due_date in the past, still open)
  * Overdue sales orders  (ship_by_date in the past, still open)

Designed to be run periodically (e.g. via cron) — it avoids creating
duplicate notifications for the same object that already have an unread
notification pending.

When CompanyConfig.email_notifications is True, also sends an email
summary to all active staff users.
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from config.models import CompanyConfig, Notification
from inventory.models import Inventory
from procurement.models import PurchaseOrder
from sales.models import SalesOrder

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate in-app notifications for low stock, overdue POs and SOs."

    def handle(self, *args, **options):
        users = list(User.objects.filter(is_active=True))
        if not users:
            self.stdout.write("No active users — nothing to do.")
            return

        today = timezone.now().date()
        created = 0
        email_lines: list[str] = []
        created += self._check_low_stock(users, email_lines)
        created += self._check_overdue_purchase_orders(users, today, email_lines)
        created += self._check_overdue_sales_orders(users, today, email_lines)
        self.stdout.write(self.style.SUCCESS(f"Created {created} notification(s)."))

        # Optionally send email summary
        config = CompanyConfig.get()
        if config and config.email_notifications and email_lines:
            self._send_email_summary(users, email_lines)

    # ── helpers ──────────────────────────────────────────────────────

    def _check_low_stock(self, users, email_lines):
        """Notify when inventory demand exceeds supply."""
        low = Inventory.objects.filter(required_cached__gt=0).select_related("product")
        count = 0
        for inv in low:
            title = f"Low stock: {inv.product.name}"
            link = reverse("inventory:inventory-detail", args=[inv.pk])
            n = self._create_for_users(
                users,
                category=Notification.Category.LOW_STOCK,
                level=Notification.Level.WARNING,
                title=title,
                message=f"Short by {inv.required_cached} unit(s).",
                link=link,
            )
            if n:
                email_lines.append(f"⚠ {title} — short by {inv.required_cached}")
            count += n
        return count

    def _check_overdue_purchase_orders(self, users, today, email_lines):
        pos = PurchaseOrder.objects.filter(
            due_date__lt=today,
        ).exclude(
            purchase_order_lines__complete=True,
        )
        open_pos = [po for po in pos if po.status == "Open"]
        count = 0
        for po in open_pos:
            title = f"Overdue PO: {po.order_number}"
            link = reverse("procurement:purchase-order-detail", args=[po.pk])
            n = self._create_for_users(
                users,
                category=Notification.Category.ORDER_OVERDUE,
                level=Notification.Level.DANGER,
                title=title,
                message=f"Due {po.due_date}, supplier: {po.supplier.name}.",
                link=link,
            )
            if n:
                email_lines.append(
                    f"🔴 {title} — due {po.due_date}, {po.supplier.name}"
                )
            count += n
        return count

    def _check_overdue_sales_orders(self, users, today, email_lines):
        sos = SalesOrder.objects.filter(
            ship_by_date__lt=today,
        )
        open_sos = [so for so in sos if so.status == "Open"]
        count = 0
        for so in open_sos:
            title = f"Overdue SO: {so.order_number}"
            link = reverse("sales:sales-order-detail", args=[so.pk])
            n = self._create_for_users(
                users,
                category=Notification.Category.ORDER_OVERDUE,
                level=Notification.Level.DANGER,
                title=title,
                message=f"Ship-by {so.ship_by_date}, customer: {so.customer.name}.",
                link=link,
            )
            if n:
                email_lines.append(
                    f"🔴 {title} — ship-by {so.ship_by_date}, {so.customer.name}"
                )
            count += n
        return count

    def _create_for_users(self, users, *, category, level, title, message, link):
        """Create a notification for each user, skipping if an unread one
        with the same title already exists for that user."""
        created = 0
        for user in users:
            if Notification.objects.filter(
                user=user, title=title, is_read=False
            ).exists():
                continue
            Notification.objects.create(
                user=user,
                category=category,
                level=level,
                title=title,
                message=message,
                link=link,
            )
            created += 1
        return created

    def _send_email_summary(self, users, email_lines):
        """Send a single digest email to each active user with an email."""
        from django.conf import settings
        from django.core.mail import send_mass_mail

        subject = f"ERPv Alert Summary — {timezone.now().strftime('%Y-%m-%d')}"
        body = "The following alerts were generated:\n\n"
        body += "\n".join(f"  • {line}" for line in email_lines)
        body += "\n\nLog in to ERPv to review and take action."

        messages = []
        for user in users:
            if user.email:
                messages.append(
                    (subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
                )

        if messages:
            try:
                send_mass_mail(messages, fail_silently=True)
                self.stdout.write(f"Sent {len(messages)} email notification(s).")
            except Exception:
                logger.exception("Failed to send email notifications")
