import pytest


@pytest.mark.django_db
class TestMainPages:
    def test_home_page(self, client):
        """Home page should render hero, CTAs and feature overview."""
        from django.urls import reverse

        resp = client.get(reverse("home"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "ERPv" in content
        assert "Features Overview" in content
        assert "/docs/" in content or "Documentation" in content
        assert "View Demo" in content
        assert "GitHub" in content

    def test_views_require_login(self, client):
        """Unauthenticated users are redirected from app dashboards."""
        from django.urls import reverse

        for url in [
            reverse("inventory:inventory-dashboard"),
            reverse("procurement:procurement-dashboard"),
            reverse("sales:sales-dashboard"),
            reverse("production:production-dashboard"),
        ]:
            resp = client.get(url)
            assert resp.status_code in (302, 301)
            assert reverse("login") in resp.url

    def test_registration_pages(self, client):
        """Registration form and completion pages render correctly."""
        from django.urls import reverse

        resp = client.get(reverse("django_registration_register"))
        assert resp.status_code == 200
        assert "Create Account" in resp.content.decode()

        resp2 = client.post(
            reverse("django_registration_register"),
            {
                "username": "newuser",
                "password1": "complexpass123",
                "password2": "complexpass123",
                "email": "new@example.com",
            },
        )
        assert resp2.status_code in (302, 301)

        completion = client.get(reverse("django_registration_complete"))
        assert "Registration Complete" in completion.content.decode()
