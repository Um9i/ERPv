"""Tests for management commands."""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command

pytestmark = pytest.mark.no_auto_permissions


class TestAssignPermissions:
    def test_grants_permissions_to_staff_users(self, db):
        staff = User.objects.create_user("cmdstaff", is_staff=True)
        assert staff.user_permissions.count() == 0

        call_command("assign_permissions")

        staff.refresh_from_db()
        codenames = set(staff.user_permissions.values_list("codename", flat=True))
        assert "manage_company" in codenames
        assert "manage_production" in codenames
        assert len(codenames) == 12

    def test_skips_non_staff_users(self, db):
        regular = User.objects.create_user("cmdregular", is_staff=False)
        call_command("assign_permissions")
        assert regular.user_permissions.count() == 0

    def test_warns_when_no_permissions_exist(self, db, capsys):
        # Delete all custom permissions to trigger the warning
        Permission.objects.filter(codename__startswith="manage_").delete()
        call_command("assign_permissions")
        captured = capsys.readouterr()
        assert "No custom permissions found" in captured.err


class TestRefreshFinanceCache:
    def test_command_runs(self, db):
        call_command("refresh_finance_cache")
