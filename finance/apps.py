from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"

    def ready(self) -> None:
        from django.db.models.signals import post_save

        from inventory.models import Inventory
        from procurement.models import PurchaseLedger
        from production.models import ProductionLedger
        from sales.models import SalesLedger

        from .signals import _refresh_finance_cache

        post_save.connect(_refresh_finance_cache, sender=SalesLedger)
        post_save.connect(_refresh_finance_cache, sender=PurchaseLedger)
        post_save.connect(_refresh_finance_cache, sender=ProductionLedger)
        post_save.connect(_refresh_finance_cache, sender=Inventory)
