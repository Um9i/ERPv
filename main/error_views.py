import logging

from django.shortcuts import render

logger = logging.getLogger(__name__)


def custom_404(request, exception):
    logger.warning("http_404", extra={"path": request.path})
    return render(request, "errors/404.html", status=404)


def custom_500(request):
    logger.error("http_500", extra={"path": request.path})
    return render(request, "errors/500.html", status=500)
