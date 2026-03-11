from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"

    def ready(self) -> None:
        from django.db.models.signals import post_save

        from inventory.models import Inventory
        from procurement.models import PurchaseLedger
        from sales.models import SalesLedger

        from .signals import _refresh_cache_on_inventory, _refresh_cache_on_ledger

        post_save.connect(_refresh_cache_on_ledger, sender=SalesLedger)
        post_save.connect(_refresh_cache_on_ledger, sender=PurchaseLedger)
        post_save.connect(_refresh_cache_on_inventory, sender=Inventory)
