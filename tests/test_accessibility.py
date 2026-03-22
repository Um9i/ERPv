"""WCAG 2.1 AA accessibility tests.

Validates skip-to-content, ARIA landmarks, table scope attributes,
visually-hidden screen reader text, icon-only button labels, and
form field accessibility across all major views.
"""

import re

import pytest
from django.contrib.auth.models import User

from config.models import CompanyConfig

pytestmark = pytest.mark.integration


def _login(client):
    user = User.objects.create_user("a11y", password="p", is_staff=True)
    CompanyConfig.objects.create(name="Test")
    client.force_login(user)
    return user


@pytest.mark.django_db
class TestSkipLink:
    """Skip-to-main-content link exists and targets #main-content."""

    def test_skip_link_present(self, client):
        _login(client)
        resp = client.get("/inventory/")
        content = resp.content.decode()
        assert 'href="#main-content"' in content
        assert "skip-to-main" in content
        assert 'id="main-content"' in content


@pytest.mark.django_db
class TestLandmarks:
    """ARIA landmarks are defined on all authenticated pages."""

    def test_nav_landmark(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'aria-label="Top navigation"' in content

    def test_aside_landmark(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'aria-label="Main navigation"' in content

    def test_main_landmark(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert "<main" in content
        assert 'id="main-content"' in content

    def test_pagination_landmark(self, client):
        _login(client)
        # Check the template directly for aria-label on pagination nav
        from pathlib import Path

        tpl = Path("templates/includes/pagination.html").read_text()
        assert 'aria-label="Pagination"' in tpl

    def test_home_footer_landmark(self, client):
        content = client.get("/").content.decode()
        assert 'role="contentinfo"' in content


@pytest.mark.django_db
class TestTableAccessibility:
    """All table headers have scope='col' for screen reader association."""

    TABLE_PAGES = [
        "/inventory/products/",
        "/procurement/po/",
        "/sales/so/",
        "/production/jobs/",
    ]

    @pytest.mark.parametrize("url", TABLE_PAGES)
    def test_th_scope_col(self, client, url):
        _login(client)
        content = client.get(url).content.decode()
        # Every <th in the response should have scope="col"
        th_tags = re.findall(r"<th\b[^>]*>", content)
        for th in th_tags:
            assert 'scope="col"' in th, f"Missing scope='col' in: {th}"


@pytest.mark.django_db
class TestIconOnlyButtons:
    """Icon-only buttons must have aria-label for screen readers."""

    def test_notification_bell_has_aria_label(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'aria-label="Notifications' in content

    def test_sidebar_logout_has_aria_label(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'aria-label="Sign out"' in content

    def test_navbar_toggle_has_aria_label(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'aria-label="Toggle navigation"' in content


@pytest.mark.django_db
class TestDecorativeIcons:
    """Decorative icons must have aria-hidden='true'."""

    def test_sidebar_icons_hidden(self, client):
        from pathlib import Path

        tpl = Path("templates/includes/sidebar_links.html").read_text()
        icons = re.findall(r'<i class="bi [^"]*"[^>]*>', tpl)
        for icon in icons:
            assert 'aria-hidden="true"' in icon, f"Missing aria-hidden: {icon}"

    def test_metric_card_icon_hidden(self, client):
        from pathlib import Path

        tpl = Path("templates/includes/metric_card.html").read_text()
        icons = re.findall(r'<i class="bi [^"]*"[^>]*>', tpl)
        for icon in icons:
            assert 'aria-hidden="true"' in icon

    def test_page_header_icon_hidden(self, client):
        from pathlib import Path

        tpl = Path("templates/includes/card.html").read_text()
        icons = re.findall(r'<i class="bi [^"]*"[^>]*>', tpl)
        for icon in icons:
            assert 'aria-hidden="true"' in icon


@pytest.mark.django_db
class TestFormAccessibility:
    """Form fields have proper label associations and error attributes."""

    def test_field_template_has_label(self):
        from pathlib import Path

        tpl = Path("templates/includes/_field.html").read_text()
        assert "for=" in tpl
        assert "id_for_label" in tpl

    def test_field_template_has_aria_describedby(self):
        from pathlib import Path

        tpl = Path("templates/includes/_field.html").read_text()
        assert "aria-describedby" in tpl

    def test_field_template_has_aria_invalid(self):
        from pathlib import Path

        tpl = Path("templates/includes/_field.html").read_text()
        assert "aria-invalid" in tpl

    def test_search_forms_have_role(self, client):
        _login(client)
        content = client.get("/inventory/").content.decode()
        assert 'role="search"' in content


@pytest.mark.django_db
class TestStatusIndicators:
    """Icon-only status indicators provide screen reader text."""

    def test_inventory_catalogue_indicator(self):
        from pathlib import Path

        tpl = Path("templates/inventory/inventory_list.html").read_text()
        # Check that the catalogue check icon has sr-only text
        assert "visually-hidden" in tpl
        assert 'aria-hidden="true"' in tpl

    def test_sales_stock_indicator(self):
        from pathlib import Path

        tpl = Path("templates/sales/sales_order_list.html").read_text()
        assert "visually-hidden" in tpl
        assert "Stock available" in tpl
        assert "Insufficient stock" in tpl

    def test_production_materials_indicator(self):
        from pathlib import Path

        tpl = Path("templates/production/production_list.html").read_text()
        assert "visually-hidden" in tpl
        assert "Materials available" in tpl
        assert "Insufficient components" in tpl


@pytest.mark.django_db
class TestBulkSelectAccessibility:
    """Bulk select checkboxes have accessible labels."""

    def test_po_select_all_has_label(self):
        from pathlib import Path

        tpl = Path("templates/procurement/purchase_order_list.html").read_text()
        assert 'aria-label="Select all orders"' in tpl

    def test_so_select_all_has_label(self):
        from pathlib import Path

        tpl = Path("templates/sales/sales_order_list.html").read_text()
        assert 'aria-label="Select all orders"' in tpl

    def test_po_row_checkbox_has_label(self):
        from pathlib import Path

        tpl = Path("templates/procurement/purchase_order_list.html").read_text()
        assert 'aria-label="Select order' in tpl

    def test_so_row_checkbox_has_label(self):
        from pathlib import Path

        tpl = Path("templates/sales/sales_order_list.html").read_text()
        assert 'aria-label="Select order' in tpl


@pytest.mark.django_db
class TestVisuallyHiddenCSS:
    """The .visually-hidden utility class exists in the stylesheet."""

    def test_visually_hidden_class_in_css(self):
        from pathlib import Path

        css = Path("static/css/styles.css").read_text()
        assert ".visually-hidden" in css
        assert "clip: rect(0, 0, 0, 0)" in css


@pytest.mark.django_db
class TestFocusStyles:
    """Focus-visible outline is defined."""

    def test_focus_visible_in_css(self):
        from pathlib import Path

        css = Path("static/css/styles.css").read_text()
        assert ":focus-visible" in css
        assert "outline:" in css


@pytest.mark.django_db
class TestDashboardNavigation:
    """Dashboard schedule navigation buttons have accessible labels."""

    def test_shipping_schedule_nav_labels(self):
        from pathlib import Path

        tpl = Path("templates/dashboards/_shipping_metrics.html").read_text()
        assert 'aria-label="Previous day"' in tpl
        assert 'aria-label="Next day"' in tpl

    def test_delivery_schedule_nav_labels(self):
        from pathlib import Path

        tpl = Path("templates/dashboards/_delivery_metrics.html").read_text()
        assert 'aria-label="Previous day"' in tpl
        assert 'aria-label="Next day"' in tpl

    def test_production_schedule_nav_labels(self):
        from pathlib import Path

        tpl = Path("templates/dashboards/_production_metrics.html").read_text()
        assert 'aria-label="Previous day"' in tpl
        assert 'aria-label="Next day"' in tpl
