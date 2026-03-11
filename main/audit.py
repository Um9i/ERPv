from django.contrib.contenttypes.models import ContentType

from main.models import AuditLog


def log_field_changes(instance, tracked_fields, user=None):
    """Compare instance values against the database and log any changes.

    Call BEFORE saving so we can read the old values from the DB.
    """
    if instance.pk is None:
        return

    try:
        old = type(instance).objects.get(pk=instance.pk)
    except type(instance).DoesNotExist:
        return

    ct = ContentType.objects.get_for_model(instance)

    for field in tracked_fields:
        old_val = getattr(old, field, None)
        new_val = getattr(instance, field, None)
        if old_val != new_val:
            AuditLog.objects.create(
                content_type=ct,
                object_id=instance.pk,
                field_name=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                changed_by=user,
            )
