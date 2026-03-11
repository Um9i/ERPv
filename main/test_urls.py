"""URL configuration that always includes admin (for testing)."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from main.views import HealthCheckView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("accounts/", include("django_registration.backends.one_step.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("inventory/", include("inventory.urls", namespace="inventory")),
    path("procurement/", include("procurement.urls", namespace="procurement")),
    path("sales/", include("sales.urls", namespace="sales")),
    path("production/", include("production.urls", namespace="production")),
    path("finance/", include("finance.urls", namespace="finance")),
    path("config/", include("config.urls", namespace="config")),
    path("dashboards/", include("dashboards.urls", namespace="dashboards")),
]
