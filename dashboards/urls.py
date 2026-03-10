from django.urls import path

from .views import DashboardHomeView, DeliveryScheduleView, ShippingScheduleView

app_name = "dashboards"

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="dashboard-home"),
    path("shipping/", ShippingScheduleView.as_view(), name="shipping-schedule"),
    path("delivery/", DeliveryScheduleView.as_view(), name="delivery-schedule"),
]
