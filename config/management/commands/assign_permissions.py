"""Assign all custom ERP permissions to existing staff users.

Run after migrating to ensure staff users retain access under the new
permission-based access control system.

Usage:
    python manage.py assign_permissions
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand

User = get_user_model()

CUSTOM_CODENAMES = [
    "manage_company",
    "manage_pairing",
    "manage_webhooks",
    "manage_products",
    "manage_stock",
    "manage_locations",
    "manage_suppliers",
    "manage_purchase_orders",
    "manage_customers",
    "manage_sales_orders",
    "manage_bom",
    "manage_production",
]


class Command(BaseCommand):
    help = "Grant all custom ERP permissions to every staff user."

    def handle(self, *args, **options):
        perms = Permission.objects.filter(codename__in=CUSTOM_CODENAMES)
        if not perms.exists():
            self.stderr.write(
                self.style.WARNING("No custom permissions found — run migrate first.")
            )
            return

        staff_users = User.objects.filter(is_staff=True)
        count = 0
        for user in staff_users:
            user.user_permissions.add(*perms)
            count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned {perms.count()} permissions to {count} staff user(s)."
            )
        )
