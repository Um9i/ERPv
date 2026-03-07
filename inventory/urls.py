from django.urls import path
from django.views.generic import TemplateView
from .views import (
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    InventoryListView,
    InventoryDetailView,
    InventoryAdjustCreateView,
    InventoryDashboardView,
    InventoryListApiView,
    LowStockListView,
    LocationListView,
    LocationCreateView,
    LocationUpdateView,
    LocationDeleteView,
    InventoryLocationCreateView,
    InventoryLocationUpdateView,
    InventoryLocationDeleteView,
    StockTransferCreateView,
)

app_name = "inventory"

urlpatterns = [
    path("", InventoryDashboardView.as_view(), name="inventory-dashboard"),
    path("low-stock/", LowStockListView.as_view(), name="inventory-low-stock"),
    path("products/create/", ProductCreateView.as_view(), name="product-create"),
    path(
        "products/<int:pk>/update/", ProductUpdateView.as_view(), name="product-update"
    ),
    path(
        "products/<int:pk>/delete/", ProductDeleteView.as_view(), name="product-delete"
    ),
    path("inventories/", InventoryListView.as_view(), name="inventory-list"),
    path("inventories/api/", InventoryListApiView.as_view(), name="inventory-list-api"),
    path(
        "inventories/<int:pk>/", InventoryDetailView.as_view(), name="inventory-detail"
    ),
    path(
        "inventories/<int:pk>/adjust/",
        InventoryAdjustCreateView.as_view(),
        name="inventory-adjust",
    ),
    # Locations
    path("locations/", LocationListView.as_view(), name="location-list"),
    path("locations/create/", LocationCreateView.as_view(), name="location-create"),
    path(
        "locations/<int:pk>/update/",
        LocationUpdateView.as_view(),
        name="location-update",
    ),
    path(
        "locations/<int:pk>/delete/",
        LocationDeleteView.as_view(),
        name="location-delete",
    ),
    # Stock location assignment (scoped to an inventory item)
    path(
        "inventories/<int:pk>/locations/add/",
        InventoryLocationCreateView.as_view(),
        name="inventory-location-add",
    ),
    path(
        "locations/assignment/<int:pk>/update/",
        InventoryLocationUpdateView.as_view(),
        name="inventory-location-update",
    ),
    path(
        "locations/assignment/<int:pk>/delete/",
        InventoryLocationDeleteView.as_view(),
        name="inventory-location-delete",
    ),
    # Stock transfers
    path(
        "inventories/<int:pk>/transfer/",
        StockTransferCreateView.as_view(),
        name="stock-transfer",
    ),
]
