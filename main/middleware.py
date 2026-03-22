import logging

from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)


class LoginRequiredMiddleware:
    """Require login for all views except a whitelist.

    Whitelist includes:
    - home page ('home')
    - account-related URLs ('/accounts/')
    - static/media files
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # ensure reverse is available
        self.exempt_urls = [reverse("home")]
        # allow any URL under accounts (login/logout/registration)
        self.exempt_prefixes = [
            "/accounts/",
            "/api/",
            "/config/api/",
            "/healthz/",
            "/inventory/api/",
            "/procurement/api/",
            "/sales/api/",
        ]

    def __call__(self, request):
        path = request.path_info
        if not request.user.is_authenticated:
            allowed = any(path == url for url in self.exempt_urls) or any(
                path.startswith(p) for p in self.exempt_prefixes
            )
            if not allowed:
                login_url = reverse("login")
                return redirect(f"{login_url}?next={request.path}")
        return self.get_response(request)
