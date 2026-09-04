"""Compatibility entry point for WSGI servers expecting app:app or wsgi:application (Render default)."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")

# Auto-collect static files on container boot if missing
staticfiles_dir = os.path.join(BASE_DIR, "staticfiles", "core")
if not os.path.exists(os.path.join(staticfiles_dir, "styles.css")):
    try:
        import django
        django.setup()
        from django.core.management import call_command
        call_command("collectstatic", interactive=False, verbosity=0)
    except Exception as e:
        pass

from schoolsoft.wsgi import application as app

application = app
