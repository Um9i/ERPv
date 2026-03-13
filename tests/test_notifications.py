import datetime

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from config.models import Notification
from inventory.models import Inventory, Product, ProductionAllocated
from procurement.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierProduct,
)
from sales.models import (
    Customer,
    CustomerProduct,
    SalesOrder,
    SalesOrderLine,
)


def _create_product(name, quantity=0):
    """Bulk-create a product with inventory + allocation (no signals)."""
    p = Product.objects.bulk_create([Product(name=name)])[0]
    Inventory.objects.bulk_create([Inventory(product=p, quantity=quantity)])
    ProductionAllocated.objects.bulk_create([ProductionAllocated(product=p)])
    return p


# ── Model tests ─────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.unit
class TestNotificationModel:
    def test_create_notification(self):
        user = User.objects.create_user("tester")
        n = Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            level=Notification.Level.WARNING,
            title="Low stock: Widget",
            message="Short by 5 units.",
        )
        assert n.pk is not None
        assert str(n) == "Low stock: Widget"
        assert n.is_read is False

    def test_default_level_is_info(self):
        user = User.objects.create_user("tester")
        n = Notification.objects.create(
            user=user,
            category=Notification.Category.ORDER_STATUS,
            title="Test",
        )
        assert n.level == Notification.Level.INFO


# ── View tests ──────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
class TestNotificationListView:
    def test_login_required(self, client):
        url = reverse("config:notification-list")
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url

    def test_list_own_notifications(self, client):
        user = User.objects.create_user("tester")
        other = User.objects.create_user("other")
        Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="My notification",
        )
        Notification.objects.create(
            user=other,
            category=Notification.Category.LOW_STOCK,
            title="Other notification",
        )
        client.force_login(user)
        response = client.get(reverse("config:notification-list"))
        assert response.status_code == 200
        notifications = response.context["notifications"]
        assert len(notifications) == 1
        assert notifications[0].title == "My notification"

    def test_empty_state(self, client):
        user = User.objects.create_user("tester")
        client.force_login(user)
        response = client.get(reverse("config:notification-list"))
        assert response.status_code == 200
        assert "No notifications yet" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.integration
class TestNotificationMarkRead:
    def test_mark_single_read(self, client):
        user = User.objects.create_user("tester")
        n = Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Test",
        )
        client.force_login(user)
        response = client.post(reverse("config:notification-mark-read", args=[n.pk]))
        assert response.status_code == 302
        n.refresh_from_db()
        assert n.is_read is True

    def test_cannot_mark_other_users_notification(self, client):
        user = User.objects.create_user("tester")
        other = User.objects.create_user("other")
        n = Notification.objects.create(
            user=other,
            category=Notification.Category.LOW_STOCK,
            title="Test",
        )
        client.force_login(user)
        response = client.post(reverse("config:notification-mark-read", args=[n.pk]))
        assert response.status_code == 404

    def test_mark_read_redirects_to_link(self, client):
        user = User.objects.create_user("tester")
        n = Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Test",
            link="/inventory/products/1/",
        )
        client.force_login(user)
        response = client.post(reverse("config:notification-mark-read", args=[n.pk]))
        assert response.status_code == 302
        assert response.url == "/inventory/products/1/"


@pytest.mark.django_db
@pytest.mark.integration
class TestNotificationMarkAllRead:
    def test_mark_all_read(self, client):
        user = User.objects.create_user("tester")
        for i in range(3):
            Notification.objects.create(
                user=user,
                category=Notification.Category.LOW_STOCK,
                title=f"Test {i}",
            )
        client.force_login(user)
        response = client.post(reverse("config:notification-mark-all-read"))
        assert response.status_code == 302
        assert Notification.objects.filter(user=user, is_read=False).count() == 0

    def test_does_not_affect_other_users(self, client):
        user = User.objects.create_user("tester")
        other = User.objects.create_user("other")
        Notification.objects.create(
            user=other,
            category=Notification.Category.LOW_STOCK,
            title="Other",
        )
        client.force_login(user)
        client.post(reverse("config:notification-mark-all-read"))
        assert Notification.objects.filter(user=other, is_read=False).count() == 1


# ── Context processor tests ────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
class TestNotificationContextProcessor:
    def test_unread_count_in_context(self, client):
        user = User.objects.create_user("tester")
        Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Unread",
        )
        Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Read",
            is_read=True,
        )
        client.force_login(user)
        response = client.get(reverse("home"))
        assert response.context["unread_notification_count"] == 1

    def test_no_count_for_anonymous(self, client):
        response = client.get(reverse("login"))
        assert "unread_notification_count" not in response.context


# ── Signal tests ────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.unit
class TestOrderStatusSignals:
    def test_sales_order_line_complete_creates_notification(self):
        user = User.objects.create_user("tester")
        product = _create_product("Widget", quantity=100)
        customer = Customer.objects.create(name="Acme")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=10
        )
        so = SalesOrder.objects.create(customer=customer)
        sol = SalesOrderLine.objects.create(
            sales_order=so, product=cp, quantity=5, complete=False
        )
        sol.quantity_shipped = 5
        sol.complete = True
        sol.save()
        assert Notification.objects.filter(
            user=user,
            category=Notification.Category.ORDER_STATUS,
            title__contains="Widget",
        ).exists()

    def test_purchase_order_line_complete_creates_notification(self):
        user = User.objects.create_user("tester")
        product = _create_product("Gadget", quantity=0)
        supplier = Supplier.objects.create(name="Supplier Co")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=5)
        po = PurchaseOrder.objects.create(supplier=supplier)
        pol = PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=10, complete=False
        )
        pol.quantity_received = 10
        pol.complete = True
        pol.save()
        assert Notification.objects.filter(
            user=user,
            category=Notification.Category.ORDER_STATUS,
            title__contains="Gadget",
        ).exists()

    def test_no_duplicate_notifications(self):
        """Completing the same line again should not create duplicates."""
        user = User.objects.create_user("tester")
        product = _create_product("Widget", quantity=100)
        customer = Customer.objects.create(name="Acme")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=10
        )
        so = SalesOrder.objects.create(customer=customer)
        sol = SalesOrderLine.objects.create(
            sales_order=so, product=cp, quantity=5, complete=False
        )
        sol.quantity_shipped = 5
        sol.complete = True
        sol.save()
        # Save again (already complete → complete, should not trigger)
        sol.save()
        count = Notification.objects.filter(
            user=user, category=Notification.Category.ORDER_STATUS
        ).count()
        assert count == 1


# ── Management command tests ────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.unit
class TestCheckNotificationsCommand:
    def test_low_stock_notification(self):
        from django.core.management import call_command

        user = User.objects.create_user("tester")
        product = _create_product("Short Item", quantity=0)
        inv = Inventory.objects.get(product=product)
        inv.required_cached = 10
        inv.save(update_fields=["required_cached"])

        call_command("check_notifications")

        assert Notification.objects.filter(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title__contains="Short Item",
        ).exists()

    def test_overdue_po_notification(self):
        from django.core.management import call_command

        user = User.objects.create_user("tester")
        product = _create_product("Part", quantity=0)
        supplier = Supplier.objects.create(name="Late Supplier")
        sp = SupplierProduct.objects.create(supplier=supplier, product=product, cost=5)
        po = PurchaseOrder.objects.create(
            supplier=supplier,
            due_date=datetime.date.today() - datetime.timedelta(days=1),
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, product=sp, quantity=10, complete=False
        )

        call_command("check_notifications")

        assert Notification.objects.filter(
            user=user,
            category=Notification.Category.ORDER_OVERDUE,
            title__contains=po.order_number,
        ).exists()

    def test_overdue_so_notification(self):
        from django.core.management import call_command

        user = User.objects.create_user("tester")
        product = _create_product("Gizmo", quantity=100)
        customer = Customer.objects.create(name="Late Customer")
        cp = CustomerProduct.objects.create(
            customer=customer, product=product, price=20
        )
        so = SalesOrder.objects.create(
            customer=customer,
            ship_by_date=datetime.date.today() - datetime.timedelta(days=1),
        )
        SalesOrderLine.objects.create(
            sales_order=so, product=cp, quantity=3, complete=False
        )

        call_command("check_notifications")

        assert Notification.objects.filter(
            user=user,
            category=Notification.Category.ORDER_OVERDUE,
            title__contains=so.order_number,
        ).exists()

    def test_no_duplicate_on_rerun(self):
        from django.core.management import call_command

        user = User.objects.create_user("tester")
        product = _create_product("Short Item", quantity=0)
        inv = Inventory.objects.get(product=product)
        inv.required_cached = 10
        inv.save(update_fields=["required_cached"])

        call_command("check_notifications")
        call_command("check_notifications")

        count = Notification.objects.filter(
            user=user,
            category=Notification.Category.LOW_STOCK,
        ).count()
        assert count == 1

    def test_no_notifications_when_no_users(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check_notifications", stdout=out)
        assert "No active users" in out.getvalue()


# ── Navbar badge tests ──────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.integration
class TestNavbarBadge:
    def test_bell_icon_shown_when_logged_in(self, client):
        user = User.objects.create_user("tester")
        client.force_login(user)
        response = client.get(reverse("home"))
        content = response.content.decode()
        assert "bi-bell" in content

    def test_badge_count_shown_when_unread(self, client):
        user = User.objects.create_user("tester")
        Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Alert",
        )
        client.force_login(user)
        response = client.get(reverse("home"))
        content = response.content.decode()
        assert "badge rounded-pill bg-danger" in content

    def test_no_badge_when_all_read(self, client):
        user = User.objects.create_user("tester")
        Notification.objects.create(
            user=user,
            category=Notification.Category.LOW_STOCK,
            title="Alert",
            is_read=True,
        )
        client.force_login(user)
        response = client.get(reverse("home"))
        content = response.content.decode()
        assert "badge rounded-pill bg-danger" not in content
