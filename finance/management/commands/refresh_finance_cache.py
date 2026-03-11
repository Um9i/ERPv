from django.core.management.base import BaseCommand

from finance.services import refresh_finance_dashboard_cache


class Command(BaseCommand):
    help = "Refresh the materialized finance dashboard aggregation cache."

    def handle(self, *args, **options):
        snapshot = refresh_finance_dashboard_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"Finance dashboard cache refreshed at {snapshot.updated_at}"
            )
        )
