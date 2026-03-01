"""main URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
#from django.views.generic import TemplateView
from django.views.generic import TemplateView
from debug_toolbar.toolbar import debug_toolbar_urls

admin.site.site_title = "ERPv 0.0.1"
admin.site.site_header = "ERPv"
# admin.site.site_url = None
admin.site.index_title = ""

urlpatterns = [
    path("admin/", admin.site.urls),
    path('accounts/', include('django_registration.backends.one_step.urls')),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("inventory/", include("inventory.urls", namespace="inventory")),
    path("procurement/", include("procurement.urls", namespace="procurement")),
    path("sales/", include("sales.urls", namespace="sales")),
    path("production/", include("production.urls", namespace="production")),
    path("finance/", include("finance.urls", namespace="finance")),
] + debug_toolbar_urls()

