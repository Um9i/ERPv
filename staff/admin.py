from django.contrib import admin
from .models import StaffProfile

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    pass
