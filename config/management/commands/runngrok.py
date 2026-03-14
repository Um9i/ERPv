"""Management command to start ngrok tunnel alongside the dev server."""

import logging
import os
import signal
import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start an ngrok tunnel and run the Django development server."

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=int(os.getenv("PORT", "8000")),
            help="Port for the dev server (default: PORT env or 8000).",
        )

    def handle(self, *args, **options):
        port = options["port"]

        # Django's autoreloader re-executes sys.argv in a child process with
        # RUN_MAIN=true.  Only the parent (reloader) process should manage the
        # ngrok tunnel; the child just needs to run the server.
        if os.environ.get("RUN_MAIN") == "true":
            # Pick up the ngrok host injected by the parent process.
            ngrok_host = os.environ.get("NGROK_HOST")
            if ngrok_host:
                from django.conf import settings

                if ngrok_host not in settings.ALLOWED_HOSTS:
                    settings.ALLOWED_HOSTS.append(ngrok_host)
                origin = f"https://{ngrok_host}"
                if origin not in settings.CSRF_TRUSTED_ORIGINS:
                    settings.CSRF_TRUSTED_ORIGINS.append(origin)
            call_command("runserver", f"0.0.0.0:{port}")
            return

        try:
            from pyngrok import conf, ngrok
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "pyngrok is not installed. "
                    "Install dev requirements: pip install -r requirements-dev.txt"
                )
            )
            sys.exit(1)

        token = os.getenv("NGROK_AUTH_TOKEN")
        if not token:
            self.stderr.write(
                self.style.ERROR(
                    "NGROK_AUTH_TOKEN not set in environment. Add it to .env."
                )
            )
            sys.exit(1)

        # Configure and open tunnel
        conf.get_default().auth_token = token
        tunnel = ngrok.connect(port, "http")
        public_url = tunnel.public_url

        self.stdout.write(self.style.SUCCESS(f"ngrok tunnel: {public_url}"))
        self.stdout.write(f"Forwarding to http://127.0.0.1:{port}")

        # Dynamically add the ngrok host to ALLOWED_HOSTS and CSRF origins
        from django.conf import settings

        ngrok_host = public_url.replace("https://", "").replace("http://", "")
        # Pass host to the autoreloader child process via environment.
        os.environ["NGROK_HOST"] = ngrok_host
        if ngrok_host not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append(ngrok_host)
        if public_url not in settings.CSRF_TRUSTED_ORIGINS:
            settings.CSRF_TRUSTED_ORIGINS.append(public_url)

        # Ensure clean shutdown
        def _shutdown(signum, frame):
            self.stdout.write("\nShutting down ngrok tunnel…")
            ngrok.disconnect(tunnel.public_url)
            ngrok.kill()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            call_command("runserver", f"0.0.0.0:{port}")
        finally:
            ngrok.disconnect(tunnel.public_url)
            ngrok.kill()
