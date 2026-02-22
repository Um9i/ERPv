from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import StaffProfile
from django.views.generic import ListView


class StaffListView(LoginRequiredMixin, ListView):
    model = StaffProfile
    template_name = 'staff/staff_list.html'
    context_object_name = 'staff_profiles'

    def get_queryset(self):
        # select_related brings in the user to avoid extra queries
        # prefetch_related handles the M2M groups on both profile and user
        return (
            StaffProfile.objects
            .select_related('user')
            .prefetch_related('groups', 'user__groups')
            .all()
        )
