from django.urls import path
from .views import (
    BOMCreateView,
    BOMUpdateView,
    BOMDeleteView,
    BOMListView,
    BOMDetailView,
    BOMItemCreateView,
    BOMItemUpdateView,
    BOMItemDeleteView,
    ProductionCreateView,
    ProductionUpdateView,
    ProductionListView,
    ProductionDetailView,
    ProductionReceivingListView,
    ProductionReceiveView,
    ProductionDashboardView,
    ProductionListApiView,
)

app_name = "production"

urlpatterns = [
    path("", ProductionDashboardView.as_view(), name="production-dashboard"),
    path("boms/", BOMListView.as_view(), name="bom-list"),
    path("boms/create/", BOMCreateView.as_view(), name="bom-create"),
    path("boms/<int:pk>/", BOMDetailView.as_view(), name="bom-detail"),
    path("boms/<int:pk>/update/", BOMUpdateView.as_view(), name="bom-update"),
    path("boms/<int:pk>/delete/", BOMDeleteView.as_view(), name="bom-delete"),
    path("bom-items/create/", BOMItemCreateView.as_view(), name="bomitem-create"),
    path("bom-items/<int:pk>/update/", BOMItemUpdateView.as_view(), name="bomitem-update"),
    path("bom-items/<int:pk>/delete/", BOMItemDeleteView.as_view(), name="bomitem-delete"),
    path("jobs/", ProductionListView.as_view(), name="production-list"),
    path("jobs/create/", ProductionCreateView.as_view(), name="production-create"),
    path("jobs/<int:pk>/", ProductionDetailView.as_view(), name="production-detail"),
    path("jobs/<int:pk>/update/", ProductionUpdateView.as_view(), name="production-update"),
    path("jobs/receiving/", ProductionReceivingListView.as_view(), name="production-receiving-list"),
    path("jobs/<int:pk>/receive/", ProductionReceiveView.as_view(), name="production-receive"),
    path("jobs/api/", ProductionListApiView.as_view(), name="production-list-api"),
]
