import csv
import sys
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import Product
from procurement.models import Supplier
from sales.models import Customer

_PRODUCT_FIELDS = {"name", "description", "sale_price", "catalogue_item"}
_CONTACT_FIELDS = {
    "name",
    "phone",
    "email",
    "website",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "postal_code",
    "country",
}


class Command(BaseCommand):
    help = "Bulk-import products, suppliers, or customers from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "model",
            choices=["product", "supplier", "customer"],
            help="Which model to import: product, supplier, or customer.",
        )
        parser.add_argument(
            "csv_file",
            help="Path to the CSV file (use '-' for stdin).",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing records matched by name instead of skipping.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the CSV without writing to the database.",
        )

    def handle(self, *args, **options):
        model_name = options["model"]
        csv_path = options["csv_file"]
        update = options["update"]
        dry_run = options["dry_run"]

        if csv_path == "-":
            reader = csv.DictReader(sys.stdin)
        else:
            try:
                fh = open(csv_path, newline="", encoding="utf-8-sig")  # noqa: SIM115
            except FileNotFoundError:
                raise CommandError(f"File not found: {csv_path}")
            reader = csv.DictReader(fh)

        model_cls, allowed_fields = {
            "product": (Product, _PRODUCT_FIELDS),
            "supplier": (Supplier, _CONTACT_FIELDS),
            "customer": (Customer, _CONTACT_FIELDS),
        }[model_name]

        # validate headers
        if reader.fieldnames is None:
            raise CommandError("CSV file appears to be empty.")
        headers = {h.strip().lower() for h in reader.fieldnames}
        if "name" not in headers:
            raise CommandError("CSV must contain a 'name' column.")
        unknown = headers - allowed_fields
        if unknown:
            raise CommandError(
                f"Unknown columns for {model_name}: {', '.join(sorted(unknown))}"
            )

        rows = list(reader)
        if csv_path != "-":
            fh.close()

        created = 0
        updated = 0
        skipped = 0
        errors = []

        with transaction.atomic():
            for i, row in enumerate(rows, start=2):
                # normalise keys
                row = {k.strip().lower(): v.strip() for k, v in row.items()}
                name = row.get("name", "").strip()
                if not name:
                    errors.append(f"Row {i}: missing name, skipped.")
                    continue

                defaults = {}
                for field in allowed_fields - {"name"}:
                    if field in row and row[field]:
                        value = row[field]
                        if model_name == "product":
                            if field == "sale_price":
                                try:
                                    value = Decimal(value).quantize(Decimal("0.01"))
                                except (ValueError, InvalidOperation):
                                    errors.append(
                                        f"Row {i}: invalid sale_price '{row[field]}'."
                                    )
                                    continue
                            elif field == "catalogue_item":
                                value = value.lower() in ("1", "true", "yes")
                        defaults[field] = value

                existing = model_cls.objects.filter(name__iexact=name).first()
                if existing:
                    if update:
                        for k, v in defaults.items():
                            setattr(existing, k, v)
                        existing.save()
                        updated += 1
                    else:
                        skipped += 1
                else:
                    obj = model_cls(name=name, **defaults)
                    obj.full_clean()
                    obj.save()
                    created += 1

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run — no changes saved."))

        for err in errors:
            self.stderr.write(self.style.WARNING(err))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} created, {updated} updated, {skipped} skipped."
            )
        )
