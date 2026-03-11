from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import CompanyConfig, Notification


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
