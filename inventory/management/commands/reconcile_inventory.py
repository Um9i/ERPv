from django.core.management.base import BaseCommand
from django.db.models import Sum

from inventory.models import Inventory, InventoryLedger


class Command(BaseCommand):
    help = (
        "Audit inventory stock levels against ledger running balances. "
        "Reports discrepancies and optionally creates adjustments to fix them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Create inventory adjustments to reconcile mismatches.",
        )

    def handle(self, *args, **options):
        fix = options["fix"]

        ledger_totals = dict(
            InventoryLedger.objects.values("product_id")
            .annotate(total=Sum("quantity"))
            .values_list("product_id", "total")
        )

        inventories = Inventory.objects.select_related("product").all()
        mismatches = []

        for inv in inventories:
            ledger_total = ledger_totals.get(inv.product_id, 0)
            if inv.quantity != ledger_total:
                mismatches.append(
                    {
                        "product": inv.product.name,
                        "product_id": inv.product_id,
                        "inventory_qty": inv.quantity,
                        "ledger_qty": ledger_total,
                        "diff": inv.quantity - ledger_total,
                    }
                )

        if not mismatches:
            self.stdout.write(
                self.style.SUCCESS("All inventory levels match ledger balances.")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Found {len(mismatches)} discrepancies:\n")
        )
        self.stdout.write(
            f"{'Product':<40} {'Inventory':>10} {'Ledger':>10} {'Diff':>10}"
        )
        self.stdout.write("-" * 72)
        for m in mismatches:
            self.stdout.write(
                f"{m['product']:<40} {m['inventory_qty']:>10} "
                f"{m['ledger_qty']:>10} {m['diff']:>+10}"
            )

        if fix:
            fixed = 0
            for m in mismatches:
                inv = Inventory.objects.get(product_id=m["product_id"])
                inv.quantity = m["ledger_qty"]
                inv.save(update_fields=["quantity"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Fixed {m['product']}: set quantity to {m['ledger_qty']}"
                    )
                )
                fixed += 1
            self.stdout.write(
                self.style.SUCCESS(f"\nReconciled {fixed} inventory records.")
            )
        else:
            self.stdout.write("\nRun with --fix to reconcile these discrepancies.")
