from django.shortcuts import redirect as _redirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(url: str, fallback: str = "/"):
    """Redirect to *url* only when it is a safe, same-origin path.

    Prevents open-redirect vulnerabilities (CWE-601) when the redirect
    target originates from user-controlled request data such as
    ``request.path`` or ``request.get_full_path()``.
    """
    if url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        return _redirect(url)
    return _redirect(fallback)
