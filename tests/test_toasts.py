import pytest
from django.contrib.auth.models import User

from config.models import CompanyConfig

pytestmark = pytest.mark.integration


@pytest.mark.django_db
class TestToastNotifications:
    """Verify that Django messages render as Bootstrap toasts."""

    def _login(self, client):
        user = User.objects.create_user("u", password="p", is_staff=True)
        CompanyConfig.objects.create(name="Test")
        client.force_login(user)
        return user

    def test_success_message_renders_toast(self, client):
        self._login(client)
        resp = client.post(
            "/config/company/",
            {"name": "Acme"},
            follow=True,
        )
        content = resp.content.decode()
        assert "toast-container" in content
        assert "app-toast" in content
        assert "app-toast-success" in content
        assert "bi-check-circle-fill" in content
        assert "Company configuration saved." in content

    def test_error_message_renders_toast(self, client):
        """Trigger an error message and verify the error toast markup."""
        self._login(client)
        from config.models import PairedInstance

        instance = PairedInstance.objects.create(
            name="Remote", url="http://remote.test/"
        )
        # Import as customer without API key → error toast
        resp = client.get(
            f"/config/paired/{instance.pk}/import-customer/",
            follow=True,
        )
        content = resp.content.decode()
        assert "app-toast-error" in content
        assert "bi-exclamation-triangle-fill" in content

    def test_toast_has_dismiss_button(self, client):
        self._login(client)
        resp = client.post(
            "/config/company/",
            {"name": "Acme"},
            follow=True,
        )
        content = resp.content.decode()
        assert 'data-bs-dismiss="toast"' in content

    def test_toast_has_autohide_delay(self, client):
        self._login(client)
        resp = client.post(
            "/config/company/",
            {"name": "Acme"},
            follow=True,
        )
        content = resp.content.decode()
        assert 'data-bs-autohide="true"' in content
        assert 'data-bs-delay="5000"' in content

    def test_no_toast_container_without_messages(self, client):
        self._login(client)
        resp = client.get("/config/company/")
        content = resp.content.decode()
        assert "toast-container" not in content

    def test_toasts_js_loaded(self, client):
        self._login(client)
        resp = client.get("/config/company/")
        content = resp.content.decode()
        assert "toasts.js" in content
