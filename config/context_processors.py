from .models import CompanyConfig, Notification


def company_config(request):
    ctx = {"company": CompanyConfig.get_or_default()}
    if hasattr(request, "user") and request.user.is_authenticated:
        ctx["unread_notification_count"] = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    return ctx
