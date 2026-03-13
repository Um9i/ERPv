from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import CompanyConfig, Notification, WebhookDelivery, WebhookEndpoint


@admin.register(CompanyConfig)
class CompanyConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not CompanyConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        instance = CompanyConfig.objects.filter(pk=1).first()
        if instance:
            return HttpResponseRedirect(
                reverse("admin:config_companyconfig_change", args=[instance.pk])
            )
        return super().changelist_view(request, extra_context)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "category", "level", "is_read", "created_at"]
    list_filter = ["category", "level", "is_read"]
    search_fields = ["title", "message"]
    readonly_fields = ["created_at"]


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ["name", "url", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "url"]
    readonly_fields = ["created_at"]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "endpoint",
        "event_type",
        "response_status",
        "success",
        "duration_ms",
        "created_at",
    ]
    list_filter = ["success", "event_type"]
    search_fields = ["endpoint__name"]
    readonly_fields = [
        "endpoint",
        "event_type",
        "payload",
        "response_status",
        "response_body",
        "success",
        "duration_ms",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
