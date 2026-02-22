from django.urls import path
from .views import StaffListView

app_name = 'staff'

urlpatterns = [
    path('users/', StaffListView.as_view(), name='users-list'),
]
